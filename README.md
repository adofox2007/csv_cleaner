# Python 命令行 CSV 数据清洗程序

这是一个仅使用 Python 标准库的通用 CSV 清洗工具。程序按命令行配置检查必填值、整数、数值范围、示例姓名格式与重复键，不依赖固定列数或固定字段名；有效记录与拒绝记录分别写入 UTF-8 CSV。

## 运行环境

- 本地验证：Windows，Python 3.10.4，PyCharm 2025.2.4
- 最低建议版本：Python 3.10（代码使用 `X | None` 类型语法）
- Git 工具：2.53.0.windows.2
- 第三方依赖：无
- 实验日期：2026-11-02（Asia/Shanghai）

项目已纳入 Git 版本控制，公开仓库为 [adofox2007/csv_cleaner](https://github.com/adofox2007/csv_cleaner)，主分支为 `main`。首次提交 `6cf2661`（`Complete CSV data cleaning project`）已推送至 `origin/main`；本轮最终一致性校对的修改尚未推送，需检查后再提交。

## 目录结构

```text
csv_cleaner/
├── clean.py
├── README.md
├── ACCEPTANCE.md
├── DEFENSE.md
├── .gitignore
├── test_results.log
├── examples/
│   ├── input.csv
│   ├── products.csv
│   ├── input_bom.csv
│   ├── input_gb.csv
│   └── expected/
│       ├── people_output.csv
│       ├── people_rejected.csv
│       ├── products_output.csv
│       └── products_rejected.csv
└── tests/
    └── test_clean.py
```

`input.csv` 有 25 条人员记录，`products.csv` 有 15 条六列商品记录。BOM 与 GB18030 文件由真实编码写入：`input_bom.csv` 的前三个字节是 `EF BB BF`；`input_gb.csv` 中中文采用 GB18030 字节，而不是仅修改扩展名。

## 快速开始

在 `csv_cleaner` 目录执行：

```bash
python clean.py --help
python clean.py --input examples/input.csv --output output.csv
```

第二条命令未配置规则，只做字段去空格和默认整行去重。拒绝文件默认写到输出文件同目录的 `rejected.csv`。

人员样例的完整规则：

```bash
python clean.py \
  --input examples/input.csv \
  --output examples/expected/people_output.csv \
  --rejected examples/expected/people_rejected.csv \
  --required id,name,age \
  --unique id \
  --integer age \
  --range age:0:150 \
  --name-field name
```

PowerShell 可将上面的反斜杠续行改为反引号，或直接写成一行。真实运行结果为 14 条有效、11 条拒绝，退出码为 1。

六列商品样例：

```bash
python clean.py \
  --input examples/products.csv \
  --output examples/expected/products_output.csv \
  --rejected examples/expected/products_rejected.csv \
  --required sku,product,price,quantity \
  --unique sku \
  --integer quantity \
  --range price:0:1000 \
  --range quantity:0:10000
```

真实运行结果为 7 条有效、8 条拒绝，退出码为 1。未设置规则的 `category` 和 `status` 字段原样保留，说明程序不依赖三列结构。

替换现场输入时，只需改变 `--input` 与 `--output`，再把规则参数中的字段名改成新 CSV 表头中的名字；增加未校验的普通列不需要修改代码。

## 命令行参数

| 参数 | 说明 |
|---|---|
| `--input PATH` | 必需，输入 CSV |
| `--output PATH` | 必需，有效记录输出 |
| `--rejected PATH` | 可选，拒绝记录输出；默认是输出目录的 `rejected.csv` |
| `--encoding NAME` | 默认 `auto`；也可指定 Python 支持的编码名 |
| `--required FIELDS` | 必填字段，逗号分隔，可重复 |
| `--unique FIELDS` | 唯一键，可用多个字段组成联合键；未给出时按整行去重 |
| `--integer FIELDS` | 整数字段，逗号分隔，可重复 |
| `--range FIELD:MIN:MAX` | 有限数值的闭区间，可重复；一侧可留空，如 `price:0:` |
| `--name-field FIELD` | 启用实验性姓名规则，可重复 |
| `-h`, `--help` | 显示帮助 |

列表参数既可写成 `--required id,name`，也可写成 `--required id --required name`。联合唯一键使用一次参数列出多个字段，例如 `--unique shop_id,sku`。

## 清洗规则

1. **编码**：自动模式依次尝试 `utf-8-sig` 与 `gb18030`。`utf-8-sig` 同时能读取普通 UTF-8 和 UTF-8 BOM；输出统一为无 BOM 的 UTF-8。
2. **空值**：每个字段先执行 `str.strip()`。必填字段的空字符串或纯空白字符串被拒绝。没有把 `NA`、`NULL`、`None` 自动视为空，避免删除可能合法的文本；如业务需要应显式扩展策略。
3. **整数**：通过 Python `int()` 校验；空值在配置该规则后也不合法。
4. **范围**：通过 `float()` 解析，并拒绝 `NaN`、正负 `Infinity`；上下界均为包含关系。
5. **姓名示例**：允许 Unicode 字母，以及连接不同字母段的单个空格、连字符、撇号或中文间隔号 `·`。不允许数字、首尾分隔符和连续分隔符。这只是本实验的示例规则，不是通用姓名标准。
6. **重复**：先完成其他校验，再登记唯一键。因此同一 ID 的第一条记录非法时，不会阻止后面的合法记录。保留第一条合法记录。
7. **未配置字段**：除首尾空白清理外保留原值，不做业务推断。

有效输出保存清理后的字段。拒绝输出保存输入记录的原字段，并增加 `error_reason`；多个原因用分号连接。CSV 读写全部通过 `csv` 模块完成，因此逗号、双引号和嵌入换行会被正确转义。

### 输入输出片段

输入：

```csv
id,name,age
1,错误1,abc
1,张伟,28
```

配置 `--unique id --integer age --range age:0:150 --name-field name` 后，有效输出为：

```csv
id,name,age
1,张伟,28
```

拒绝输出包含：

```csv
id,name,age,error_reason
1,错误1,abc,age: not an integer; age: not numeric; name: invalid demonstration name format
```

## 编码处理的准确含义

自动模式是候选解码策略，不是统计意义上的编码检测器。ASCII 字节同时是 UTF-8 和 GB18030 的合法子集，因此这种文件会报告第一个成功候选 `utf-8-sig`；某些其他编码的字节也可能被 GB18030 解码成错误字符。知道来源编码时应显式传入，例如：

```bash
python clean.py --input examples/input_gb.csv --output gb_output.csv --encoding gb18030
```

无法按候选或指定编码解码时，错误写入 stderr，退出码为 3。

## 退出码

| 退出码 | 含义 | 示例 |
|---:|---|---|
| 0 | 成功且无拒绝记录 | 全部记录合法或只有表头 |
| 1 | 清洗完成，但存在拒绝记录 | 规则失败或重复记录 |
| 2 | 参数或规则配置错误 | 字段不存在、范围倒置、路径冲突 |
| 3 | 输入、编码或 CSV 格式错误 | 文件不存在、列数不一致、引号未闭合 |
| 4 | 输出写入错误 | 输出目录不存在或目标不可替换 |

退出码 1 不是程序故障：两个结果文件均已成功生成。退出码 2–4 表示清洗未正常完成。预期会返回 1 的命令在 shell 自动化中需要显式接受该状态。

## 输出安全与异常边界

- 整个输入会先严格解析并完成规则校验，之后才开始写输出。列数不一致、坏引号、坏编码、空文件等情况不会产生部分清洗结果。
- 输入、有效输出、拒绝输出的规范化路径必须两两不同。
- 两个输出先分别写入目标目录中的临时文件，刷新到磁盘后再用 `os.replace()` 替换目标，降低单文件半写入风险。
- 两个输出文件不能作为一个跨文件事务同时更新：第一个替换成功后，第二个替换仍可能失败。程序对此返回 4，并在本文明确披露此限制。
- 输出目录必须预先存在，程序不会猜测并自动创建目录。
- 空文件属于输入格式错误；只有表头是合法输入，会生成只有表头的两个输出。
- 表头不能为空或重复；规则字段名必须与表头精确匹配。
- 普通异常不会向用户打印 Python 堆栈，只输出分类错误信息到 stderr。

## 自动化测试

运行：

```bash
python -m unittest discover -s tests -v
```

Python 3.10.4 / PyCharm 2025.2.4 本地验证结果为 `Ran 21 tests in 2.688s`、`OK`。最终提交前又执行了一次完整复核，实际结果为 `Ran 21 tests in 1.864s`、`OK`，退出码 0；这次复核的完整输出保存在 `test_results.log`。测试使用项目内自动清理的临时目录隔离数据，并通过 `subprocess` 实际运行 `clean.py`。

覆盖范围包括：综合清洗、UTF-8/BOM/GB18030/手动编码、全合法数据、非法记录不占唯一键、规则字段不存在、错误规则、输入缺失、列数错误、坏引号、不可解码、输出目录缺失、替换失败、路径冲突、空文件和只有表头、六列商品、姓名边界、已有输出保护、特殊字符、重复运行一致性、非有限数字和联合唯一键。5 种退出码均有断言。

重新生成真实日志（PowerShell）：

```powershell
python -m unittest discover -s tests -v *> test_results.log
$LASTEXITCODE
```

日志应显示 21 项测试及最终 `OK`。不要手工编辑日志来改变结果。

## 关键设计选择

- **标准库而非 pandas**：本题是流式 CSV 规则校验与 CLI 工程练习，标准库部署成本为零，退出码和错误分类更直接。当前实现为保证写前完整验证把记录保存在内存中，并非真正流式处理。
- **规则由字段名配置**：表头和行宽在运行时读取，所有列均动态保留，因此不是针对 `id,name,age` 硬编码。
- **校验先于去重**：避免坏记录抢占键，这是样例中同 ID 非法/合法两行的必要语义。
- **严格 CSV 解析**：使用 `strict=True` 并额外检查每行列数，防止 `DictReader` 静默吸收多列或少列。
- **临时文件 + 原子替换**：保护单个已有文件不被半写入；同时诚实说明两个文件无法获得单事务保证。

## 局限性

- 自动编码候选只覆盖 UTF-8/BOM 和 GB18030，不能可靠识别任意编码。
- 为保证格式错误时不写部分结果，当前实现将整个文件读入内存；超大文件需要两遍扫描或数据库/外部排序方案。
- 数值范围使用二进制浮点数；金融金额若要求精确小数语义，应改用 `decimal.Decimal`。
- 不自动识别分隔符、表头别名、日期、布尔值、区域化数字或业务缺失标记。
- 姓名规则只是可选演示，无法覆盖全球所有真实姓名。
- 两个输出文件无法跨文件原子提交。
- `error_reason` 是拒绝文件的保留输出列名；输入表头不应将其用作业务列名。

## 复现实验

从项目目录依次执行：

```bash
python --version
git --version
python clean.py --help
python -m unittest discover -s tests -v
```

然后运行前述人员和商品样例命令。预期分别得到 `14/11` 与 `7/8` 的有效/拒绝计数。详细验收证据见 [ACCEPTANCE.md](ACCEPTANCE.md)，现场讲解提纲见 [DEFENSE.md](DEFENSE.md)。

仓库复现方式：

```bash
git clone https://github.com/adofox2007/csv_cleaner.git
cd csv_cleaner
python -m unittest discover -s tests -v
```
