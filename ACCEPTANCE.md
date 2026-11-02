# 最终验收记录

验收日期：2026-11-02（Asia/Shanghai）。以下结论均对应实际文件和已执行命令。

| 评分维度 | 分值 | 完成情况 | 对应证据 | 验证结果 |
|---|---:|---|---|---|
| 正确性与边界验证 | 40 | 完成 | `clean.py`、`tests/test_clean.py`、四个预期输出 | 21 项端到端测试通过；编码、空值、去重、非法值、CSV 边界及 5 种退出码均覆盖 |
| 实现与目标库集成 | 20 | 完成 | `clean.py`、六列 `examples/products.csv` | 纯标准库 CLI；字段名和列数动态处理；商品样例 7 条通过、8 条拒绝 |
| 可复现实验依据 | 25 | 完成 | `README.md`、`test_results.log`、`examples/` | 环境、命令、真实编码、输入、输出和日志齐全；测试日志最终为 `OK` |
| 讲解与分析 | 15 | 完成 | `README.md`、`DEFENSE.md` | 记录设计取舍、边界、结果差异及局限 |

按题目给出的 100 分检查表，所有要求均已有对应交付物，可自评为 **100/100（材料完整）**。这是一份按验收项的自查，不替代导师最终评分。

## 实际执行记录

```text
python --version
Python 3.14.0

git --version
git version 2.53.0.windows.2

python -m unittest discover -s tests -v
Ran 21 tests in 1.925s
OK
```

人员命令实际返回退出码 1，并报告：

```text
accepted=14; rejected=11
```

商品命令实际返回退出码 1，并报告：

```text
accepted=7; rejected=8
```

退出码 1 符合“成功完成但存在拒绝记录”的约定，不是测试失败。

## 文件检查

- 新增：`clean.py`、`README.md`、`ACCEPTANCE.md`、`DEFENSE.md`、`.gitignore`、`test_results.log`。
- 新增测试：`tests/test_clean.py`。
- 新增输入：四个 `examples/*.csv`，其中 BOM 与 GB18030 均为真实编码。
- 新增真实运行输出：`examples/expected/` 下四个 CSV。
- 删除：无。
- 工作区其他既有项目：未修改。

## 尚存问题

没有阻止交付的已知失败；已知限制已完整列在 README。最重要的限制是自动编码仅为候选策略、超大文件会占用与输入规模成比例的内存、两个输出无法跨文件原子提交。
