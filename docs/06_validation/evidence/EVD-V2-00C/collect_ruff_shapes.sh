#!/usr/bin/env bash
# STEP-00C S0C.1/S0C.4 的本地读数采集器：**只采集，不判定**。
# 为什么要有这个文件：本机按约定不装依赖（无 venv、无 ruff、无 make），所以 CI 的 `ruff check app tests`
# 这一读数不可能在这里产出；这里能产出的是「本机那张 stdlib 近似表在改前/改后各报了哪些 I001」
# 与「那三条 ruff 真报过的形状现在长成什么样」。两者都是可重跑的，号数一律现打，不抄进任何文档。
#
# 用法：bash docs/06_validation/evidence/EVD-V2-00C/collect_ruff_shapes.sh > 本目录 out_ruff_shapes.txt
# 依赖：git + python3（stdlib）。不写仓库任何被测文件；旧版近似表只取到系统临时目录。
set -u
cd "$(git rev-parse --show-toplevel)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export PYTHONIOENCODING=utf-8

run() { printf '\n$ %s\n' "$*"; "$@" 2>&1; }

FILES=$(find apps/api/app apps/api/tests -name '*.py' | sort | tr '\n' ' ')
COUNT=$(printf '%s\n' $FILES | grep -c .)

echo "采集时点：$(git rev-parse --short HEAD)（$(date -Iseconds)）｜$(uname -s)"
echo "工具在场性：ruff=$(command -v ruff || echo 无) gitleaks=$(command -v gitleaks || echo 无) make=$(command -v make || echo 无)"
echo "被扫的仓库侧 .py 文件数（现算）：$COUNT"

echo
echo "########## 1 旧版近似表（HEAD 那份 g24）在同一棵树上的 I001 读数"
git show HEAD:docs/06_validation/evidence/EVD-V2-00/g24_static_check.py > "$TMP/g24_old.py"
# 只走 `check()`，不走那份脚本的 main：main 会把路径往它自己的 ROOT 上 relative_to，
# 而临时副本的 parents[4] 不是仓库根——那会一路落进 INCONCLUSIVE 分支，读数变成「0 条」，
# 那是采集器自己造的假绿（第一版就真的踩在这里）。
python - "$TMP/g24_old.py" $FILES <<'PY' 2>&1 | sed 's/^/  /'
import importlib.util, pathlib, sys
spec = importlib.util.spec_from_file_location("g24_old", sys.argv[1])
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
n = 0
for f in sys.argv[2:]:
    for v in m.check(pathlib.Path(f)):
        if " I001 " in v:
            print(v)
            n += 1
print(f"旧版 I001 计数：{n}")
PY

echo
echo "########## 2 新版近似表（工作树这份）在同一棵树上的 I001 读数"
python - docs/06_validation/evidence/EVD-V2-00/g24_static_check.py $FILES <<'PY' 2>&1 | sed 's/^/  /'
import importlib.util, pathlib, sys
spec = importlib.util.spec_from_file_location("g24_new", sys.argv[1])
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
n = 0
for f in sys.argv[2:]:
    for v in m.check(pathlib.Path(f)):
        if " I001 " in v:
            print(v)
            n += 1
print(f"新版 I001 计数：{n}")
PY

echo
echo "########## 3 近似表自己的两端自证（该报的 12 项 + 该静默的 3 项）"
python docs/06_validation/evidence/EVD-V2-00/g24_static_check.py --self-test 2>&1 | sed 's/^/  /'

echo
echo "########## 4 ruff 真报过的那三条 I001：改前形状（取自 65f508b）与改后形状（工作树）"
for spec in "test_chat_sse.py:18" "test_env_isolation.py:28" "test_kb_longlink_ingest.py:41"; do
  f=${spec%%:*}; n=${spec##*:}
  echo "--- $f（65f508b:$n → 工作树同一段）"
  git show "65f508b:apps/api/tests/$f" | sed -n "$((n-1)),$((n+1))p" | sed 's/^/  改前: /'
  grep -n "from conftest import\|from fixtures.wechat_urls import\|^import pytest" "apps/api/tests/$f" \
    | head -4 | sed 's/^/  改后: /'
done

echo
echo "########## 5 已知的一处方向性差异：ruff 的 E501 有 pragma 例外，本表按总长一律报"
for spec in "test_kb_orphan_purge.py:91" "test_manifest_sync.py:481" "test_metadata_filter.py:174" "test_metadata_filter.py:233"; do
  f=${spec%%:*}; n=${spec##*:}
  sed -n "${n}p" "apps/api/tests/$f" | python -c "
import sys
l = sys.stdin.buffer.read().decode('utf-8').rstrip('\n')
i = l.find('#')
print(f'  $f:$n  总长 {len(l)}｜注释前 {i}｜尾部 {l[-30:]!r}')
"
done
echo "  对照：evidence/65f508b/ruff_65f508b.txt 里 ruff 0.12.12 报的 E501 只有 1 条（test_env_isolation.py:68），"
echo "  上面这四处它一条没报——四处都是「代码段不超限、只有 pragma 注释把整行推过去」的形状。"

echo
echo "########## 6 真实工具两步的缺失分支（make 不在本机，跑的是 Makefile 里那段同构 shell）"
bash -c 'set -e; missing=0;
if command -v ruff >/dev/null 2>&1; then echo "跑 ruff"; else echo "SKIP(tool missing) ruff"; missing=1; fi
if command -v gitleaks >/dev/null 2>&1; then echo "跑 gitleaks"; else echo "SKIP(tool missing) gitleaks"; missing=1; fi
if [ "$missing" -ne 0 ]; then echo "退出码 3（不是 PASS 也不是 FAIL）"; exit 3; fi
echo "全过"'
echo "  实测退出码：$?（Makefile 目标本身本机无法干跑——make 也不在这台机器上）"

echo
echo "########## 7 本机仍证明不了的那一半（登记为交人工/交 CI，不写成本地通过）"
cat <<'TXT'
  - `ruff check app tests` 在 96e8f31+ 之后的真实读数：要 venv（README §5 的 J-1/J-2 同一条通道）。
  - `gitleaks detect`：`.gitleaksignore` 的 6 个历史指纹不许猜，必须有二进制实跑 ⇒ 属 D-12 拍板后的动作。
  - `ruff format --check`：非阻断（13 份文件历史上未格式化），本卡只把它从 lint-backend 里拆出来。
TXT
