# code-only サイトの配布境界

この candidate は合成 snapshot 専用の build-only GitHub Actions 用コード。
`ci/synthetic-dry-run-*` branch への push 以外では起動しない。
commit/push/実 CI は親 operator が担当し、production deploy は含めない。

## 配布するもの

| パス | 責務 |
| --- | --- |
| `theme/styles/miya.css`、`theme/styles/fonts.css` | owned CSS と自己配信フォント宣言 |
| `theme/client/dune`、`theme/client/hero.ml` | 新しい active client の OCaml ソース |
| `theme/layout/` | 静的な信頼済み fragment。snapshot 本文をテンプレート評価しない |
| `theme/assets/` | allowlist のライセンス済み font/notice。実ノート添付物ではない |
| `theme/notices/` | ソースコードのライセンス・出所説明。生成 artifact へは非配布 |
| `config/pins.json` | 固定 Forester 6.0~dev と reviewed converter の real build driver |
| `config/synthetic-inputs.json` | 合成のみの immutable content revision / manifest SHA-256 / HOME_ID |
| `config/theme.json` | 明示した asset / compiled-client mapping。snapshot 由来設定を禁止 |
| `scripts/` | source-only client compiler、synthetic preflight、native renderer、最終 audit |
| `test/` | 合成 schema/privacy/owned-CSS/workflow/distribution 回帰と browser harness |
| `.github/workflows/synthetic-dry-run.yml` | deployment-free push workflow |
| root の Dune/Nix config と `dune.lock/` | 固定依存。移動・solve・version の手編集を行わない |
| `wrangler.jsonc` | inert の将来用 Workers 設定。今回の workflow は呼ばない |

## 含めないもの

旧 Git history、旧 `legacy/` / `site/` / generated output、credential cache、実 Markdown
vault、実ノート本文、入力 snapshot のコピー、機械固有の acceptance inventory/log を含めない。
元 worktree の archive や Git index を読む回帰はこの code-only 配布の tests と分離する。
ライセンス済み assets の由来として残る旧ソース相対パス・コード commit/hash は
private note bytes や機械固有の成功証跡ではない。

`_build/` と `dist/` は Git 管理外。合成 input checkout も workflow が別パスへ取得する。
root Dune の `(dirs :standard \ tools legacy)` と explicit source-only allowlist を維持する。
旧 builder、XML/XSL navigation、vault/attachment copier、`--dev` は使用しない。

## 起動と gate

`config/synthetic-inputs.json` の固定 schema と `dataset: synthetic-only` を検査する。
未提供の revision/digest/home を `null` のまま実行すると `SW_SYNTHETIC_INPUT` で拒否し、
content checkout や runner output の作成へ進まない。承認済み値を入れても、独立した
null fixture / malformed fixture による fail-closed 回帰は維持する。
branch/event/repository の逸脱は `SW_SYNTHETIC_SCOPE`、converter pin/driver の逸脱は
`SW_PIN` で拒否する。ID の綴り、digest の case、original JSON bytes を修復・正規化しない。

`PUBLIC_CONTENT_TOKEN` は approved-content checkout の一箇所だけに指定する。
job-wide env には入れず、site/converter/compiler に渡さない。
全 checkout は `persist-credentials: false`、depth 1、submodules/LFS 無効。
read-only permissions、no cache、audited synthetic HTML/assets だけの一日 artifact とし、
deploy/Pages/Wrangler/Cloudflare の実行を追加しない。

## 検証の区別

```sh
python3 -B -m unittest discover -s test -p 'test*.py' -v
python3 -B test/forester_version_test.py
```

`test_owned_css_leak.py` は CI でも明示実行する。
real locked compiler は別の opt-in、native renderer は明示した binary の opt-in とする。
unit PASS、fresh client compile、native build、new-byte browser acceptance、hosted CI は
それぞれ別の判定。古い成功報告や単なる Dune target discovery を新 build の成功に流用しない。
検証ログと full distribution inventory は source tree 外で親が保管する。
