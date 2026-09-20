# Pack1実CIA 読み取り専用調査レポート

## 対象

ユーザー所有の`Taiko Drum Master Dokodon! Mystery Adventure_Base_DLC_Pack1.cia`を対象にした。解析はファイルを読み取るだけで行い、CIA、NCCH、RomFS、SongInfo、MusicInfoの変更・再パック・変換・抽出物のGit登録は行っていない。

| 項目 | 確認値 |
| --- | --- |
| ファイルサイズ | 132,376,448 bytes |
| SHA-256 | `655942fd605efc326ad1d8e7913af8c1b552e3a30548eb7d6c0233333d9373b7` |
| Title ID | `0004008c00190e00` |
| Content数 | 78（index 0～77） |
| 検出曲枠 | 77（index 1～77） |
| NCCH product code | `CTR-M-BT8J-00`（全78 Content） |
| 暗号化状態 | 全78 ContentがTMD type `0x0000`、未暗号化として解析可能 |
| RomFSファイル数 | 1,445 |
| 実機確認 | 未実施 |

## 調査方法

1. CIA headerからcertificate、ticket、TMD、content、metaの境界を算出した。
2. TMDのcontent recordを読み、各contentのindex、ID、type、size、SHA-256を検証した。
3. 未暗号化NCCHのRomFS領域からIVFC level 3を特定し、directory/file metadata tableを走査した。
4. RomFSのpath、絶対offset、size、ファイル単位SHA-256だけを収集した。ゲーム資産本体は保存していない。
5. 各contentの`SongInfo.dat`、`MusicInfo.dat`、譜面・音声・タイトルresourceのpathと内部参照を相互検査した。
6. 実データのバイト列をコピーせず、同じ構造条件を表す小さな合成fixtureで回帰テストを作成した。

## CIA・Content構成

CIA sectionはheader 8,224 bytes、certificate 2,560 bytes、ticket 848 bytes、TMD 6,564 bytes、content領域132,358,144 bytesだった。TMDにはindex 0～77の78 recordがあり、実contentのサイズとhashが一致した。

全contentはNCCHとして認識でき、同一product codeとIVFC RomFSを持つ。index 0はPack全体のmetadataに相当する14ファイルのarchiveで、index 1～77は曲単位のRomFS構造を持つ。過去情報の「78 contents / 77 song slots」は期待値として採用せず、このCIAから再確認した値をprofileへ記録した。

## RomFS構造

readerはIVFC headerとlevel 3 filesystem headerを検証し、親・兄弟・子参照をたどってUTF-16LE名からpathを構築する。各fileについてpath、offset、size、SHA-256を診断JSONへ出す。

以下を破損として停止する。

- header、metadata entry、file dataの範囲外参照またはoverflow
- metadata領域の重複
- directory/file sibling chainや親参照の循環
- 不正・未到達entry、hash table pointerの不正
- 同一または大文字小文字だけが異なる重複path
- file data領域を越えるoffsetとsize

## 曲枠構造

index 1～77の各contentから、content index/ID、内部ID、SongInfo、MusicInfo、main/preview audio、難易度別譜面、title resourceを対応付けた。全77枠でEasy、Normal、Hard、Oni、main audio、preview audio、title resourceを確認した。index 21だけは通常Oniに加えて`ex_..._m.bin`形式のUra譜面を持つ。

表示曲名だけでは識別せず、TMDのcontent identity、RomFSの内部ID、SongInfo record key、MusicInfo keyの組み合わせを使用する。`slots.json`の曲枠一覧は上記CIA SHA-256から生成した構造metadataであり、ゲームファイル本体を含まない。

## SongInfoで確認できたこと

全77枠を比較し、次を共通構造として確認した。

- record countは1、record offsetは`0x10`
- pointerは6個で、先頭文字列領域は`0x50`以降
- pointer前の固定領域には10個の32-bit値があるが、意味は未解明のためunknownとして保持
- pointerは厳密な昇順かつファイル内で、文字列は次のpointer境界までにUTF-8 NUL終端する
- 文字列0はrecord key、1は表示名、2はMusicInfo key、3は譜面directory keyとして全枠を横断検証
- 必須参照の空文字、不正UTF-8、非ゼロpaddingはERROR

## MusicInfoで確認できたこと

全77枠でrecord count 1、record offset `0x10`、3個の文字列pointerを確認した。文字列0はSongInfoのMusicInfo keyと一致し、文字列1と2はそれぞれmain/preview audioのRomFS pathへ解決した。pointer前の5個の32-bit値は意味を推測せずunknownとして保持する。

## 確認された参照不整合

content index 69（content ID `516810f8`）では、SongInfoの譜面keyが`akb437`なのに対し、実際の譜面directoryと他の内部参照は`akb347`だった。これはparserの推測補正対象にせず、`PACK1_CHART_KEY_MISMATCH`としてERRORを維持する。

このため、対象SHA-256は読み取り診断用fingerprintとして`SUPPORTED`だが、参照検査全体は`FAIL`になる。`SUPPORTED`は書換え可能・実機互換・安全な置換枠という意味ではない。

## Fingerprint

Pack1判定ではSHA-256だけに依存せず、Title ID、content count、index集合、全contentのNCCH/RomFS主要構造、product codeを確認する。

- `SUPPORTED`: 構造がprofileと一致し、記録済みSHA-256とも一致
- `COMPATIBLE_BUT_UNVERIFIED`: 構造は一致するがSHA-256は未登録
- `UNSUPPORTED`: Title ID、content構成または主要構造が不一致
- `CORRUPT`: 安全に構造を読めない

## 未解明事項

- SongInfoの10個、MusicInfoの5個のunknown 32-bit fieldの意味
- content index 69の不一致が元データ仕様か別要因か
- 実機でのロード条件、キャッシュ、署名・再パック要件
- audio/NAACの完全なcontainer・codec仕様と容量制約
- 譜面binaryの完全な意味、TJAからの安全な変換条件
- どの枠を置換可能と扱うべきかという保護方針

## 次Milestoneで使用可能な情報

読取専用のCIA/NCCH/RomFS境界、77枠の安定identity、SongInfo→MusicInfo→audioとSongInfo→chartの参照検査は、slot allocatorの入力モデルと追加調査の土台にできる。一方、既知の参照ERRORと未実機検証があるため、まだ音声生成、曲置換、RomFS/CIA書換え、再パックへは進めない。
