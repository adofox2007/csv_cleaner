from __future__ import annotations

import csv
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "clean.py"


class CleanerCLITests(unittest.TestCase):
    def setUp(self) -> None:
        # Keep isolated test data inside the project so restricted CI/sandbox
        # environments do not redirect the OS temp directory to a denied path.
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT / "tests")
        self.work = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write(self, name: str, text: str, encoding: str = "utf-8") -> Path:
        path = self.work / name
        path.write_text(text, encoding=encoding, newline="")
        return path

    def run_clean(self, input_path: Path, *arguments: str, output: Path | None = None):
        output_path = output or self.work / "output.csv"
        command = [
            sys.executable,
            str(CLEAN),
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            *arguments,
        ]
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        return subprocess.run(
            command,
            text=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=20,
            check=False,
        ), output_path

    def rows(self, path: Path):
        with path.open(encoding="utf-8", newline="") as stream:
            return list(csv.DictReader(stream))

    def test_01_comprehensive_cleaning(self):
        source = self.write(
            "input.csv",
            "id,name,age\n1,Bad1,abc\n1, 张伟 ,28\n2,,20\n3,李娜,-1\n"
            "4,王芳,151\n5,王五,30\n5,重复,31\n6,赵六,40\n",
        )
        result, output = self.run_clean(
            source,
            "--required", "id,name,age",
            "--unique", "id",
            "--integer", "age",
            "--range", "age:0:150",
            "--name-field", "name",
        )
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual([r["id"] for r in self.rows(output)], ["1", "5", "6"])
        rejected = self.rows(self.work / "rejected.csv")
        self.assertEqual(len(rejected), 5)
        self.assertIn("not an integer", rejected[0]["error_reason"])
        self.assertIn("duplicate key", rejected[-1]["error_reason"])

    def test_02_utf8_bom_encoding(self):
        source = self.work / "bom.csv"
        source.write_bytes("id,name\n1,中文\n".encode("utf-8-sig"))
        result, output = self.run_clean(source, "--required", "name")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.rows(output)[0]["name"], "中文")
        self.assertIn("encoding=utf-8-sig", result.stdout)

    def test_03_gb18030_encoding(self):
        source = self.work / "gb.csv"
        source.write_bytes("id,name\n1,中文\n".encode("gb18030"))
        result, output = self.run_clean(source)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.rows(output)[0]["name"], "中文")
        self.assertIn("encoding=gb18030", result.stdout)

    def test_04_manual_encoding(self):
        source = self.write("ascii.csv", "id,value\n1,plain\n", "ascii")
        result, _ = self.run_clean(source, "--encoding", "ascii")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_05_all_valid_and_whitespace_is_trimmed(self):
        source = self.write("valid.csv", "id,value\n 1 , alpha \n2,beta\n")
        result, output = self.run_clean(source, "--required", "id,value")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.rows(output), [
            {"id": "1", "value": "alpha"}, {"id": "2", "value": "beta"}
        ])
        self.assertEqual(self.rows(self.work / "rejected.csv"), [])

    def test_06_invalid_row_does_not_reserve_unique_key(self):
        source = self.write("keys.csv", "id,age\n1,bad\n1,20\n")
        result, output = self.run_clean(
            source, "--unique", "id", "--integer", "age", "--range", "age:0:120"
        )
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.rows(output), [{"id": "1", "age": "20"}])

    def test_07_missing_configured_field_is_exit_2(self):
        source = self.write("fields.csv", "id,value\n1,x\n")
        result, _ = self.run_clean(source, "--required", "missing")
        self.assertEqual(result.returncode, 2)
        self.assertIn("not found", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_08_bad_rule_and_unknown_encoding_are_exit_2(self):
        source = self.write("rules.csv", "id,value\n1,2\n")
        bad_range, _ = self.run_clean(source, "--range", "value:9:1")
        bad_encoding, _ = self.run_clean(source, "--encoding", "definitely-not-a-codec")
        self.assertEqual(bad_range.returncode, 2)
        self.assertEqual(bad_encoding.returncode, 2)

    def test_09_missing_input_is_exit_3(self):
        result, _ = self.run_clean(self.work / "absent.csv")
        self.assertEqual(result.returncode, 3)
        self.assertIn("cannot read", result.stderr)

    def test_10_inconsistent_column_count_is_exit_3(self):
        source = self.write("columns.csv", "a,b\n1,2\n3\n")
        result, _ = self.run_clean(source)
        self.assertEqual(result.returncode, 3)
        self.assertIn("columns", result.stderr)

    def test_11_malformed_quotes_are_exit_3(self):
        source = self.write("quotes.csv", 'a,b\n1,"unterminated\n')
        result, _ = self.run_clean(source)
        self.assertEqual(result.returncode, 3)
        self.assertIn("CSV", result.stderr)

    def test_12_undecodable_input_is_exit_3(self):
        source = self.work / "binary.csv"
        source.write_bytes(b"a,b\n\x80\x80\n")
        result, _ = self.run_clean(source)
        self.assertEqual(result.returncode, 3)
        self.assertIn("decode", result.stderr)

    def test_13_missing_output_directory_is_exit_4(self):
        source = self.write("input.csv", "a,b\n1,2\n")
        result, _ = self.run_clean(source, output=self.work / "absent" / "out.csv")
        self.assertEqual(result.returncode, 4)
        self.assertIn("directory", result.stderr)

    def test_14_replace_failure_is_exit_4(self):
        source = self.write("input.csv", "a,b\n1,2\n")
        output_directory = self.work / "destination"
        output_directory.mkdir()
        result, _ = self.run_clean(
            source,
            "--rejected", str(self.work / "separate-rejected.csv"),
            output=output_directory,
        )
        self.assertEqual(result.returncode, 4)
        self.assertIn("replace", result.stderr)

    def test_15_input_output_conflict_is_exit_2(self):
        source = self.write("same.csv", "a,b\n1,2\n")
        result, _ = self.run_clean(source, output=source)
        self.assertEqual(result.returncode, 2)
        self.assertIn("must be different", result.stderr)

    def test_16_empty_and_header_only_inputs(self):
        empty = self.write("empty.csv", "")
        empty_result, _ = self.run_clean(empty)
        self.assertEqual(empty_result.returncode, 3)

        header = self.write("header.csv", "a,b\n")
        header_result, output = self.run_clean(header)
        self.assertEqual(header_result.returncode, 0, header_result.stderr)
        self.assertEqual(output.read_text(encoding="utf-8"), "a,b\n")

    def test_17_six_column_product_data(self):
        source = ROOT / "examples" / "products.csv"
        result, output = self.run_clean(
            source,
            "--required", "sku,product,price,quantity",
            "--unique", "sku",
            "--integer", "quantity",
            "--range", "price:0:100000",
            "--range", "quantity:0:10000",
        )
        self.assertEqual(result.returncode, 1, result.stderr)
        rows = self.rows(output)
        self.assertEqual(len(rows[0]), 6)
        self.assertEqual(next(r for r in rows if r["sku"] == "A009")["status"], "new, featured")
        self.assertTrue(any("not numeric" in r["error_reason"] for r in self.rows(self.work / "rejected.csv")))

    def test_18_name_rule_boundaries(self):
        source = self.write(
            "names.csv",
            "id,name\n1,马·云\n2,Jean-Luc\n3,O'Connor\n4,阿里··木\n5,Alice2\n6,·开头\n",
        )
        result, output = self.run_clean(source, "--name-field", "name")
        self.assertEqual(result.returncode, 1)
        self.assertEqual([r["id"] for r in self.rows(output)], ["1", "2", "3"])

    def test_19_existing_outputs_protected_on_bad_input(self):
        source = self.write("bad.csv", "a,b\n1\n")
        output = self.write("output.csv", "OLD OUTPUT\n")
        rejected = self.write("rejected.csv", "OLD REJECTED\n")
        result, _ = self.run_clean(source, output=output)
        self.assertEqual(result.returncode, 3)
        self.assertEqual(output.read_text(encoding="utf-8"), "OLD OUTPUT\n")
        self.assertEqual(rejected.read_text(encoding="utf-8"), "OLD REJECTED\n")

    def test_20_special_characters_and_repeatability(self):
        source = self.write(
            "special.csv",
            'id,note\n1,"comma, quote ""and"" newline\ncontinued"\n2,plain\n2,plain\n',
        )
        result1, output = self.run_clean(source)
        first_output = output.read_bytes()
        first_rejected = (self.work / "rejected.csv").read_bytes()
        result2, _ = self.run_clean(source)
        self.assertEqual((result1.returncode, result2.returncode), (1, 1))
        self.assertEqual(output.read_bytes(), first_output)
        self.assertEqual((self.work / "rejected.csv").read_bytes(), first_rejected)
        self.assertIn("newline\ncontinued", self.rows(output)[0]["note"])

    def test_21_non_finite_numbers_and_combined_unique_key(self):
        source = self.write(
            "numbers.csv", "group,id,value\na,1,NaN\na,1,2\na,1,3\nb,1,Infinity\nb,1,4\n"
        )
        result, output = self.run_clean(
            source, "--unique", "group,id", "--range", "value:0:10"
        )
        self.assertEqual(result.returncode, 1)
        self.assertEqual([(r["group"], r["value"]) for r in self.rows(output)], [("a", "2"), ("b", "4")])
        reasons = [r["error_reason"] for r in self.rows(self.work / "rejected.csv")]
        self.assertTrue(any("not finite" in reason for reason in reasons))
        self.assertTrue(any("duplicate key" in reason for reason in reasons))


if __name__ == "__main__":
    unittest.main()
