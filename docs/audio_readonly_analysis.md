# Audio / NAAC Read-Only Analysis

## 調査対象

Milestone 3では、SHA-256
`655942fd605efc326ad1d8e7913af8c1b552e3a30548eb7d6c0233333d9373b7`
のユーザー所有Pack1 CIAに含まれる77曲枠を対象に、main 77参照とpreview 77参照を読み取り専用で全数調査した。154参照は154個の固有NAACファイルだった。ゲームデータや音声本体はリポジトリへ保存していない。

本資料の用語は次のように区別する。

- `Observed`: 対象Pack1の実ファイルから読み取った事実。
- `CONFIRMED`: 独立した仕様根拠または振る舞いの検証まで得たもの。
- `STRONGLY_CORRELATED`: 複数ファイルで候補値と測定値が完全一致したが、意味までは確定していないもの。
- `POSSIBLE`: 一致するが、値の変化がないなど相関根拠が不足するもの。
- `UNKNOWN`: 意味を決定できないもの。
- `Device tested`: 今回は該当なし。

## 調査方法

既存CIA parser、RomFSの`absolute_offset`/`size`、Pack1 catalogの`main_audio`/`preview_audio`、単一のimmutable `SourceSnapshot`を再利用した。NAACを一括コピーして保持せず、各範囲を`memoryview`で順に解析し、ヘッダーraw bytesと統計だけを保持する。

payload境界は4096を前提にせず、ADTS sync候補から最低3連続フレームを検証し、さらに候補からファイル末尾まで全フレームを厳格にparseできる位置として決定した。単発の`0xFFF`は採用しない。ADTS parserはframe length、CRC header長、sample-rate index、channel configuration、layer、次sync、末尾余剰bytes、stream途中のformat変更を検査する。

durationは各frameの`1024 * (number_of_raw_data_blocks_in_frame + 1)`を合計してsample rateで割り、bitrateはADTS実バイト数×8÷durationから求める。設定上のnominal bitrateは使用しない。

## NAAC観測構造

- 154/154ファイルでpayload offsetとobserved header sizeは4096 bytesだった。
- これは「verified Pack1 samplesで全数観測」の意味であり、NAAC一般仕様が4096 bytesを要求するとは認定していない。
- 154ヘッダーの4096位置中、1085位置が全ファイルで同一だった。main内では1091位置、preview内では2033位置が同一だった。同一byteはfield意味の証明ではない。
- 全ファイルの先頭にはASCII `AAC `が観測された。0x2CのLE u32は全154件で48だったが、fieldの意味はUNKNOWNである。
- 0x18、0x19、0x1A、0x22はmain内・preview内ではそれぞれ定数だがrole間で異なった。意味不明のrole-specific patternとしてWARNINGにした。
- raw headerは解析中に保持して比較するが、JSONのper-file recordにはサイズとSHA-256だけを出し、ヘッダー本体や音声payloadは出力しない。

## ADTS構造

ADTS profileはAudio Object Typeそのものではない。観測値`profile=1`は`AOT=profile+1=2`であり、AOT 2をAAC-LCと解釈した。MPEG IDは0をMPEG-4、1をMPEG-2として別々に保存する。bit fieldの実装はFFmpeg公式の[`adts_header.c`](https://github.com/FFmpeg/FFmpeg/blob/master/libavcodec/adts_header.c)とも照合した。

154/154 streamを末尾までparseでき、truncation、途中format変更、未解明末尾bytesは0件だった。全streamでCRCなし、`number_of_raw_data_blocks_in_frame=0`を観測した。

## Main / Preview比較

| 観測項目 | main（77） | preview（77） |
|---|---:|---:|
| sample rate | 32000 Hz: 77 | 32000 Hz: 77 |
| channels | 2: 77 | 2: 77 |
| profile / AOT | profile 1 / AOT 2 / AAC-LC: 77 | profile 1 / AOT 2 / AAC-LC: 77 |
| MPEG ID | 0: 37、1: 40 | 0: 30、1: 47 |
| CRC | none: 77 | none: 77 |
| frame count | 2264～5056 | 469固定 |
| duration | 72.448～161.792秒 | 15.008秒固定 |
| measured bitrate | 92,265.965～119,930.494 bps | 64,417.910～119,542.644 bps |
| observed header size | 4096: 77 | 4096: 77 |

32 kHz、stereo、AAC-LCは全154件で一致したObservedであり、ゲームが生成音声へ必須とする条件や3DS実機互換性の保証ではない。MPEG IDはmain/preview双方で混在しているため、単一versionへ正規化する根拠はない。

## Header field analysis

`CONFIRMED`として意味を確定したNAAC header fieldはない。

`STRONGLY_CORRELATED`:

- MPEG ID 0の67/67件で、0x10のLE u32がADTSから算出したdecoded nominal samplesと一致した。
- MPEG ID 0の67/67件で、0x24のLE u32がADTS payload sizeと一致した。
- 0x10を含む重複幅の解釈や0x11からのscaled値も機械的には一致するため、最小限の候補だけを上記へ記した。重複解釈は別fieldの証明ではない。

`POSSIBLE`:

- preview 77件では0x10がdecoded nominal samplesと一致した。ただし全previewが同じ469 framesで値が変化しないため、preview単独では相関を証明できない。
- 0x0Cのaligned LE u32は全154件で32000だった。全対象のsample rateも32000固定なので一致はObservedだが、値の変化を使った相関検証はできない。

`UNKNOWN`:

- MPEG ID 1 mainに対するsize/sample関連fieldの規則。
- 上記以外のheader領域の意味。
- signature/versionらしき定数の正式な意味。

## Seek table調査結果

seek tableとして`CONFIRMED`されたものはない。

MPEG ID 0の67/67件では、0x30から始まる4-byte little-endian、payload-relativeの単調増加配列がADTS frame startと100%一致した。MPEG ID 1の87件では同じ候補を検出しなかった。候補entry countは469～1012、frame intervalは1が30件、2が4件、3が27件、4が6件だった。

この配列はframe boundaryとの`STRONGLY_CORRELATED`なseek-like candidateである。ただし実際のseek動作を検証していないため、`seek_table = confirmed`とはしない。

## Sample count / delay / padding

ADTSから計算できるdecoded nominal samplesは確定的に報告できる。MPEG ID 0コホートでは0x10候補と67/67一致したが、MPEG ID 1 mainへ一般化できない。

playable sample count、encoder delay、末尾padding、およびそれらを区別するheader fieldはすべてUNKNOWNである。ADTS nominal samplesとの一致を、再生対象sample数やgapless metadataの確定と読み替えない。

## Historical hypotheses

- 4096-byte header: 154/154でObserved。一般仕様としては未確定。
- 32 kHz: 154/154でObserved。必須条件としては未確定。
- stereo: 154/154でObserved。必須条件としては未確定。
- AAC-LC: 154/154でADTS profile/AOTからObserved。実機生成条件としては未確定。
- MPEG version: 単一ではなく、MPEG-4（ID 0）が67件、MPEG-2（ID 1）が87件。

## Optional decoder validation

外部decoderによるfull decodeは`NOT_RUN`。Milestone 3の必須条件にはせず、PC decoder成功を3DS hardware compatibilityとは扱わない。

## 未解決事項

- MPEG ID 1 headerのsample/size metadata規則。
- seek-like candidateの実際のconsumerとseek semantics。
- encoder delay、padding、playable samples。
- 未知header領域のfield境界と意味。
- 新規生成物の3DS実機互換性。

## 次Milestoneへの条件

判定は`MORE_AUDIO_RESEARCH_REQUIRED`。

既存154ファイルは完全に読み取れるが、安全なNAAC候補生成にはMPEG ID 1 header規則、delay/padding、seek-like配列の生成・消費規則が未解決である。`audio_profiles.json`は変更せず、production encoding profileおよびdevice-tested profileは追加していない。write compatibilityは引き続き`BLOCKED`である。
