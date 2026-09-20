# Taiko Mystery Adventure Pack1 Custom Song Builder

ユーザー所有の「太鼓の達人 ドコドン！ミステリーアドベンチャー」日本版DLC Pack1を、安全に診断し、将来カスタム曲へ置換するためのWindows向けプロジェクトです。

現在の実装範囲はMilestone 0～2です。**CIA・RomFS・SongInfoを書き換える機能はなく、完全に読み取り専用です。** 音声変換、NAAC生成、tja2fumen接続、slot allocator、GUI、EXE化も未実装です。

## 実装済み

- CIAヘッダー、証明書、Ticket、TMD、Content、Metaの境界解析
- Title ID、content index/ID/type/size、SHA-256の診断
- 未暗号化NCCHヘッダー、ExeFS/RomFS領域、IVFC magicの安全な確認
- 安定ID（content index、content ID、内部ID）を前提とする型付きSongCatalog基盤
- 実ポインタからのSongInfo文字列読取、範囲・NUL終端・空必須値・参照存在検査
- UTF-8/CP932を厳格にデコードするTJA Lexer/Parser/Validator/Normalizer
- `Decimal`によるBPM/OFFSET/DELAY/SCROLL、`Fraction`によるMEASURE保持
- 空白なし命令、複数行小節、Easy～Ura、Unicode TITLE/WAVEの処理
- 入力CIAのSHA-256と原子的JSON診断レポート

Pack1固有の曲枠とSongInfoスキーマは、実データで認定されるまで空のままです。暗号化Contentは鍵なしで推測解析せず、`encrypted_not_inspected`と報告します。

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

コンソールには診断状態、Title ID、検出曲数、ERROR数、WARNING数を表示します。JSONは`--output`を明示した場合だけ生成し、入力CIAの隣へ勝手に書きません。

終了コードはPASSが`0`、警告ありが`1`、診断ERRORが`2`、入力を読めない場合が`3`です。静的検証と実機検証は区別され、実機状態は常に`NOT_TESTED`です。

## TJA診断

```powershell
.\.venv\Scripts\python.exe -m app.main tja-check "example.tja"
```

未知命令、壊れたMEASURE、未終端小節などは行・列・元テキスト付きERRORになります。Normalizerは空白を統一しますが、値やノーツを別の意味へ変換しません。

## テスト

実ゲームデータや実楽曲は使用せず、合成CIA/NCCH、合成SongInfo、短い自作TJAだけを使用します。

```powershell
.\.venv\Scripts\python.exe -m pytest
```

## 安全上の制約

- CIA、3DS/CCI、Ticket、秘密鍵、音源、NAACはGit管理対象外です。
- 入力をin-place変更するコードはありません。
- 未知命令や不明構造を黙って無視しません。
- 静的PASSを3DS実機互換性の保証として表示しません。
- 秘密鍵の取得・配布機能はありません。

次工程へ進む前に、ユーザー所有Pack1 CIAから読み取り専用レポートを取得し、Title ID、NCCH暗号化状態、曲枠、SongInfoポインタ構造を認定する必要があります。
