# Taiko Mystery Adventure Pack1 Custom Song Builder

ユーザー所有の「太鼓の達人 ドコドン！ミステリーアドベンチャー」日本版DLC Pack1を、安全に診断し、将来カスタム曲へ置換するためのWindows向けプロジェクトです。

現在の実装範囲はMilestone 0～2.5です。**CIA・RomFS・SongInfoを書き換える機能はなく、完全に読み取り専用です。** 音声変換、NAAC生成、tja2fumen接続、slot allocator、GUI、EXE化も未実装です。

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

Pack1固有の構造は、記録済みSHA-256のユーザー所有CIAから読み取り専用で認定しています。ただし、content index 69には実データ由来のSongInfo/chart key不一致があり、診断は意図的にERRORを返します。`SUPPORTED`は読取診断への対応を表すだけで、書換えや実機動作を保証しません。詳細は[`docs/pack1_real_diagnostics.md`](docs/pack1_real_diagnostics.md)を参照してください。暗号化Contentは鍵なしで推測解析せず、`encrypted_not_inspected`と報告します。

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

次工程では既知のcontent index 69参照不一致を安全方針へ反映し、書換え前提ではないslot allocator設計と音声仕様の追加調査が必要です。現時点では曲置換、音声生成、再パックへ進めません。
