# Taiko Mystery Adventure Pack1 Custom Song Builder

ユーザー所有の「太鼓の達人 ドコドン！ミステリーアドベンチャー」日本版DLC Pack1を、安全に診断し、将来カスタム曲へ置換するためのWindows向けプロジェクトです。

現在の実装範囲はMilestone 0～3です。**CIA・RomFS・SongInfo・NAACを書き換える機能はなく、完全に読み取り専用です。** 音声変換、NAAC生成、tja2fumen接続、slot allocator、GUI、EXE化も未実装です。

## 実装済み

- CIAヘッダー、証明書、Ticket、TMD、Content、Metaの境界解析
- Title ID、content index/ID/type/size、SHA-256の診断
- 未暗号化NCCHヘッダー、ExeFS/RomFS領域、IVFC magicの安全な確認
- IVFC RomFSのディレクトリ・ファイル表、offset、size、SHA-256の境界検査付き読取
- 安定ID（content index、content ID、内部ID）を前提とする型付きSongCatalog基盤
- 実Pack1で確認した77曲枠とSongInfo/MusicInfo参照の読取・整合性検査
- Title ID、content構成、NCCH/RomFS構造を組み合わせたPack1 fingerprint
- UTF-8/CP932を厳格にデコードするTJA Lexer/Parser/Validator/Normalizer
- `Decimal`によるBPM/OFFSET/DELAY/SCROLL、`Fraction`によるMEASURE保持
- 空白なし命令、複数行小節、Easy～Ura、Unicode TITLE/WAVEの処理
- 入力CIAのSHA-256と原子的JSON診断レポート
- 1回の読込で固定するimmutable `SourceSnapshot`と、read/write compatibilityの独立した安全ゲート
- TJAの構文妥当性とターゲット変換可能性を分離したconversion gate
- strict ADTS frame parserと、連続frame検証によるNAAC payload境界検出
- Pack1 main/preview全参照のread-only audio scan、実測bitrate、header相関、seek-like候補のレポート

Pack1固有の構造は、記録済みSHA-256のユーザー所有CIAから読み取り専用で認定しています。content index 69のSongInfo/chart key不一致は、値が完全一致するときだけ`KNOWN_BASELINE_ANOMALY`としてWARNINGに分類し、情報を保持したまま置換不可にします。少しでも値が異なれば通常のERRORです。

`read compatibility: SUPPORTED`は読み取り対応だけを意味します。writer未実装・実機未認定のため、`write compatibility`は常に`BLOCKED`であり、書換えや実機動作を保証しません。詳細は[`docs/pack1_real_diagnostics.md`](docs/pack1_real_diagnostics.md)を参照してください。暗号化Contentは鍵なしで推測解析せず、`encrypted_not_inspected`と報告します。

## 開発環境

Python 3.11以上を使用します。確認環境はPython 3.14です。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pip install -e .
```

## CIA診断

```powershell
.\.venv\Scripts\python.exe -m app.main diagnose "path\to\base.cia" --output "work\diagnostic_report.json"
```

コンソールには診断状態、Title ID、検出曲数、ERROR数、WARNING数を表示します。JSONは`--output`を明示した場合だけ生成し、入力CIAの隣へ勝手に書きません。JSONにはfingerprint、RomFSファイルメタデータ、曲枠、参照検査結果を含みますが、ファイル本体は含みません。

CIAは最初の1回だけ`bytes`へ読み込み、そのSnapshotから全解析・SHA-256・SongInfo/MusicInfo読取を行います。JSONのsource情報は標準でファイル名だけです。絶対パスが必要なローカル用途に限り、`--include-source-path`を明示してください。

終了コードはPASSが`0`、警告ありが`1`、診断ERRORが`2`、入力を読めない場合が`3`です。静的検証と実機検証は区別され、実機状態は常に`NOT_TESTED`です。

## TJA診断

```powershell
.\.venv\Scripts\python.exe -m app.main tja-check "example.tja"
```

未知命令、壊れたMEASURE、未終端小節などは行・列・元テキスト付きERRORになります。Normalizerは空白を統一しますが、値やノーツを別の意味へ変換しません。`TJA SYNTAX`と`TARGET CONVERSION`は別判定です。Branch、GOGO、BARLINE、`#START P1`、負のDELAYは構文上VALIDでも、意味が認定されるまで変換は`BLOCKED`です。

TJA終了コードは、構文VALIDかつ変換可能で警告なしが`0`、構文VALIDだが変換BLOCKEDまたは警告ありが`1`、構文INVALIDが`2`、ファイル・decode・runtime errorが`3`です。

## Audio診断

```powershell
.\.venv\Scripts\python.exe -m app.main audio-scan "path\to\Pack1.cia" --output "work\audio_scan.json"
```

catalogのmain/preview参照を全数走査し、NAAC payload offset、ADTS format、全frame統計、実測平均bitrate、header field相関、seek-like候補をJSONへ記録します。入力CIA、NAAC、AACは一切変更しません。既存Pack1の観測結果は[`docs/audio_readonly_analysis.md`](docs/audio_readonly_analysis.md)を参照してください。

終了コードはPASSが`0`、観測上のvariationや既知Pack1 anomalyによるWARNINGが`1`、音声解析ERRORが`2`、入力・runtime errorが`3`です。`--include-source-path`を指定しない限り、JSONへ絶対パスを含めません。

## テスト

実ゲームデータや実楽曲は使用せず、合成CIA/NCCH、合成SongInfo、短い自作TJAだけを使用します。

```powershell
.\.venv\Scripts\python.exe -m pytest
```

ユーザー所有の実CIAによるprivate integrationは、ローカルでのみ環境変数を設定すると実行されます。未設定のCIではSKIPされ、CIAをGitHub Secretsやartifactへ送信しません。

```powershell
$env:TAIKO_PACK1_TEST_CIA = "C:\path\to\Pack1.cia"
.\.venv\Scripts\python.exe -m pytest tests\integration\test_real_pack1.py
.\.venv\Scripts\python.exe -m pytest tests\integration\test_real_pack1_audio.py
```

## 安全上の制約

- CIA、3DS/CCI、Ticket、秘密鍵、音源、NAACはGit管理対象外です。
- 入力をin-place変更するコードはありません。
- `SUPPORTED`をwriterの許可判定として使用しません。write gateは常に`BLOCKED`です。
- IVFC writerへ進む前に、現在未実装のIVFC hash tree完全性検証が必要です。
- 未知命令や不明構造を黙って無視しません。
- 静的PASSを3DS実機互換性の保証として表示しません。
- 秘密鍵の取得・配布機能はありません。

既存Pack1の全音声は読み取り可能になりましたが、MPEG ID 1のNAAC header規則、delay/padding、seek-like配列の意味は未解決です。判定は`MORE_AUDIO_RESEARCH_REQUIRED`であり、現時点では曲置換、音声生成、slot allocator本実装、RomFS/CIA書換え、再パックへ進めません。
