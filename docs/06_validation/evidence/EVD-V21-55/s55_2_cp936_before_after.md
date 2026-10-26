S55.2 补：`_match` 之外，覆盖率门在这台机器上还有第二条复算不了的因
====================================================================

P-125 登记的是键形失配（八个阈值键各命中 0 个）。把键形修好之后，附录 A 第五节那条命令
**照原样**（仓库根、不设任何编码变量）在本机仍然是红的——红因与判据无关，纯粹是控制台编码：

```
$ python scripts/check_module_coverage.py --json apps/api/coverage.json      # 默认 cp936 流
rc_plain=1        ← 判据全过之后仍然 rc=1
```

末段原文（逐字，`>` 之后是本卡改后）：

```
  达标   88.94%  ≥ 79.0%  TOTAL
Traceback (most recent call last):
  File "D:\Code\AideanBotHot\scripts\check_module_coverage.py", line 185, in <module>
    sys.exit(main())
             ^^^^^^
  File "D:\Code\AideanBotHot\scripts\check_module_coverage.py", line 178, in main
    print("\u2705 ȫģȫִ")
UnicodeEncodeError: 'gbk' codec can't encode character '\u2705' in position 0: illegal multibyte sequence
```

同一条命令、同一份 coverage.json，只加 `PYTHONIOENCODING=utf-8` ⇒ `rc_utf8=0`，末行
`✅ 全部模块与全局达标` 正常打印。**八个模块逐行都印了"达标"，然后在末行崩掉**——
这台机器的控制台语言在决定门的结果，而这道门的判据一个都没参与。

## 为什么这属于本卡、而不是另开一张

卡面 3 目标②写的是"本机任何平台都能按附录 A 原样复算模块覆盖率门"。上面这条让那句话在 @win
不成立；允许面第 10 格列的就是 `scripts/check_module_coverage.py`。同一条命令形式、同一个文件、
同一个目标，所以在这里修，不外另开 P 号。

## 修法

脚本末段 `if __name__ == "__main__":` 里把 stdout 编码钉成 utf-8（`errors="replace"`），外面套一层
`isinstance(sys.stdout, io.TextIOWrapper)`：

- **为什么有这层 isinstance**：第一版直接写 `sys.stdout.reconfigure(...)`，`mypy app ../../scripts`
  判红 `union-attr: Item "TextIO" of "TextIO | Any" has no attribute "reconfigure"`
  （本链第二跑 `rc_mypy=1`，原文 `s55_local_gates_pass2.txt` 的 mypy 段——这条不是笔误，是门抓到的：
  `reconfigure` 只在 `TextIOWrapper` 上存在，`sys.stdout` 的类型是抽象的 `TextIO`）。
  加了 isinstance 收窄后 mypy 绿，语义也更诚实：流被人换成别的对象时**如实跳过**，不假装钉上了。
  那条"跳过"的路径不靠这里自证，由下面的常驻用例在真子进程里钉住（真子进程的 stdout 就是 TextIOWrapper）。
- 判红那侧同样受益：末行 `❌`（U+274C）在 cp936 上也编不出来，**真判红时**会把诊断信息一起崩掉，
  rc 还是 1（碰巧与判红同码，最难查的那种"读数与原因对不上"）。
- 放在 `__main__` 而不是 `main()`：in-process 单测走 capsys，脚本不该改测试进程的流编码。
- CI 的 ubuntu 本就是 utf-8，这一步对它没有可观察差别（`ci.yml` 那一步的读数是同一条门的权威源）。
- 顺带一次自我打回：`import subprocess`/`import sys` 我先在函数内写了一遍、又提到模块级，
  ruff 判 `F401 imported but unused` 两处，而 `tests/test_workflow_gate_wiring.py:98` 会跑
  `entry.py lint-backend` ⇒ 本机全量连带 1 failed（第二跑 `rc_ruff=1 / rc_pytest=1`，
  红因就是这一条，不是新功能有问题；原文 `s55_local_gates_pass2.txt`）。删掉函数内那两行后
  `test_module_coverage_gate.py` + `test_workflow_gate_wiring.py` **20 passed**。

## 常驻用例与它的先红

`apps/api/tests/test_module_coverage_gate.py::test_gate_survives_a_non_utf8_console`：用
`PYTHONIOENCODING=gbk` 起子进程跑真脚本（不依赖本机 locale，Linux 上 gbk 码表同样是 Python 自带的），
断言 rc=0 **且** stdout 里有"全部模块与全局达标"那行——只看 rc 会被"一条都没判"骗过去。

摘掉编码钉后的红（原文 `s55_probe_f_pytest.txt`）：

```
E       AssertionError: rc=1
E         ...（八个模块的"达标"行都在，末行崩）
E       UnicodeEncodeError: 'gbk' codec can't encode character '\u2705' in position 0: illegal multibyte sequence
```

装回编码钉后：该文件 **16 passed**（原 11 + S55.2 键形 4 + 这条 1）。

## 顺带核实：这不是所有门的通病

同一台机器、同样不设编码变量：`python scripts/check_docs_consistency.py` ⇒ **rc=0**（中文照旧乱码显示，
但那些字符都在 cp936 里，打印不抛）。所以这是 `check_module_coverage.py` 末行那两枚表情符号自己的问题，
不是"本仓所有 stdlib 门在 @win 都不可复算"——那句话现在没有证据。

## 改后（同一台机器、同一条命令、仍然不设任何编码变量）

```
$ python scripts/check_module_coverage.py --json apps/api/coverage.json
rc_plain_after=0
末两行原文：  达标   88.91%  ≥ 79.0%  TOTAL
               ✅ 全部模块与全局达标
```

（这份 `coverage.json` 是那条门链中断前那次 pytest 的产物，TOTAL 与最终读数的差在 ±0.03 的
抖动带内——那个抖动本身有记录（AGENTS.md 测试段），所以这里只用它证"末行不再崩"，
不用它当覆盖率判据；当判据的读数在 `s55_local_gates_final.txt`。）

判红那侧同修（`--set` 是卡面第 8 格给的反证通道，只用来证明门真会拦，CI 不使用）：

```
$ python scripts/check_module_coverage.py --json apps/api/coverage.json --set app/services/kb.py=99.99
rc_red=1
末行原文：❌ 覆盖率门判红/判 NOT-PASS（rc=1）
```

改前这一侧会在**打印这行本身**时抛 `UnicodeEncodeError`（`❌` 同样编不出来）：rc 仍是 1，
但末行诊断丢失，而"rc=1 且没有诊断"与"判据真判红"在读数上分不开。现在红是因判红，不是因崩。
