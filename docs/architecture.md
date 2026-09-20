# Architecture through Milestone 2.6

```text
CLI
 ├─ CIA diagnostic job
 │   ├─ immutable SourceSnapshot（single read + SHA-256）
 │   ├─ CIA/TMD/content reader（Snapshot view only）
 │   ├─ optional unencrypted NCCH/RomFS inspection
 │   ├─ SongInfo/MusicInfo reader（Snapshot range only）
 │   ├─ profile-backed SongCatalog
 │   ├─ baseline anomaly classifier
 │   ├─ read compatibility ─┐
 │   ├─ write compatibility ├─ safety gate → atomic JSON report
 │   └─ corrupt diagnostics ┘
 └─ TJA check
     └─ strict decode → lexer → parser/typed AST → validator → normalizer
                                               └─ conversion eligibility gate
```

## Immutable source boundary

`SourceSnapshot.from_path()`はCIAを1回だけimmutable `bytes`へ読み込み、その同じbytesからsizeとSHA-256を確定する。CIA/TMD/NCCH/RomFS readerとSongInfo/MusicInfo analyzerはSnapshotのread-only `memoryview`または範囲readだけを使用する。診断開始後に元ファイルが置換されても、1件のレポート内でSnapshotが混在しない。

`read_cia(path)`は既存API用wrapperであり、診断jobは明示的に1個のSnapshotを作って`read_cia_snapshot()`へ渡す。

## Compatibility gate

Read compatibilityは`SUPPORTED`、`COMPATIBLE_BUT_UNVERIFIED`、`UNSUPPORTED`、`CORRUPT`を表す。これは解析能力だけの判定である。Write compatibilityは別モデルで、writer・実機認定・置換方針が未完成のMilestone 2.6では常に`BLOCKED`となる。

将来のwrite gateはTitle ID、content count/index/ID/size、product code、NCCH/RomFS構造、slot identity、SongInfo/MusicInfo schema、known baseline anomalyの一致をすべて独立に検査する。readの`SUPPORTED`だけでwriteを許可してはならない。

構造破損はI/O errorと区別する。読み込めたbytesのCIA/RomFS構造が壊れている場合はschema version 2の診断JSONを生成し、read=`CORRUPT`、write=`BLOCKED`とする。ファイル不存在やアクセス拒否は入力/runtime errorのまま扱う。

## TJA conversion gate

`syntax_valid`は構文ERRORがないこと、`conversion_eligible`は現在認定済みの意味だけで安全に変換できることを表す。Branch、GOGO、BARLINE、START argument、負のDELAYは構文を保持できてもconversion blockerになる。未知命令などの構文ERRORも必ず変換をBLOCKする。

## Known baseline anomaly

content 69の`akb437`→`akb347`不一致は、profileに記録したcontent index・code・両keyが完全一致するときだけ`KNOWN_BASELINE_ANOMALY` WARNINGになる。元のcode/detailsは保持し、枠はprotectedかつreplacement不許可とする。別contentまたは別keyは通常ERRORである。

Both paths are read-only. No writer, transcoder, allocator, GUI, or packaging path exists in these milestones.

IVFC hash treeの完全性検証は未実装である。IVFC/RomFS writer、NCCH writer、CIA再パックへ進む前の必須安全ゲートとして残す。
