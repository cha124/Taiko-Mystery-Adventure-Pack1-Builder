# Taiko Mystery Adventure Pack1 Custom Song Builder

Windows向けカスタム曲ビルダーの、安全性を優先した実装です。現在は **Milestone 1: Diagnostic Core** までを対象とし、CIAを書き換えません。

## 現在できること

- CIAヘッダー、証明書、Ticket、TMD、Content、Metaの境界解析
- TMDのTitle IDとContent recordの解析
- Content index、Content count、サイズ、重複、切り詰めの検査
- 入力CIA全体と各ContentのSHA-256計算
- 機械可読なJSON診断レポート
- Pack1プロファイルの認定状態表示

SongInfoや曲枠の実オフセットは未確認値を推測せず、プロファイルが認定されるまでは `NOT_TESTED` と報告します。秘密鍵を要求せず、暗号化Contentの復号やCIAの変更は行いません。

## 実行

```powershell
python -m app.main diagnose "path\to\base.cia" --output "output\diagnostic.json"
```

終了コードは、PASSが`0`、警告ありが`1`、診断エラーが`2`、入力自体を読めない場合が`3`です。`--output`を省略した場合は標準出力へJSONを出します。

## テスト

テストは著作物を含まない合成バイト列だけを使います。

```powershell
python -m unittest discover -s tests -v
```

## 安全上の制約

- CIA、音源、鍵、ユーザーの曲データはGit管理対象外です。
- 入力CIAをin-place変更するコードはありません。
- 静的診断のPASSを実機互換性の保証として表示しません。
- Pack1固有のプロファイル値は、検証済みデータから確定するまで未認定です。

今後はTJA parser、Audio/NAAC、batch slot allocator、SongInfo/title、CIA writer、独立再検証、GUIの順に追加します。

