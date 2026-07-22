# ADR-0001: VOICEVOX ENGINE 0.25.2 と個人音量・抑揚設定

## Status

Accepted

## Context

TalkBot2 は Docker Compose で VOICEVOX ENGINE を起動し、Discord の各利用者に
話者と話速を保存して読み上げています。現行の Compose は
`voicevox/voicevox_engine:nvidia-ubuntu20.04-latest` を指定しています。

公式 GitHub の Latest リリースは **VOICEVOX ENGINE 0.25.2**（2026-04-30）です。
Docker Hub には Linux/amd64 向けの
`voicevox/voicevox_engine:nvidia-ubuntu24.04-0.25.2` が公開されています。
一方、現行の Ubuntu 20.04 の `latest` タグは 2025-05-10 更新です。

現在の `VoicevoxClient.create_audio()` は、`/audio_query` が返した AudioQuery の
`speedScale` だけを書き換えて `/synthesis` に渡します。ENGINE 0.25.2 の
AudioQuery には `intonationScale`（全体の抑揚）と `volumeScale`（全体の音量）も
必須の浮動小数点フィールドとして含まれ、`/audio_query` の初期値は両方 `1` です。

個人設定の保存・キュー投入は、既に `user_speakers` と `user_speeds` を Discord
ユーザー ID ごとに JSON へ保存し、メッセージをキューに入れる時点で値をスナップ
ショットしています。この方式を音量・抑揚にも適用する。

## Decision Drivers

- 指定された ENGINE 0.25.2 を再現可能な形で導入する。
- 利用者ごとに音量と抑揚を保持し、他の利用者に影響させない。
- ENGINE が生成した AudioQuery を基に、公式 API のフィールドだけを変更する。
- 既存の `config.json` を手動移行なしで読み込めるようにする。
- 読み上げ待ちメッセージの設定を、後から変更した個人設定で変化させない。

## Considered Options

### ENGINE イメージ

1. `nvidia-ubuntu24.04-0.25.2` に固定する。
2. `nvidia-latest` を使用する。
3. 現行の `nvidia-ubuntu20.04-latest` を維持する。

### 個人設定の保存先

1. 既存 `config.json` にユーザー ID ごとのマップを追加する。
2. ENGINE のプリセット API を使用する。
3. サーバー（guild）単位の設定にする。

## Decision

1. `docker/docker-compose.yml` の ENGINE イメージを
   `voicevox/voicevox_engine:nvidia-ubuntu24.04-0.25.2` に変更する。浮動の
   `latest` タグではなく、リリース番号を含むタグを使用する。
2. Discord スラッシュコマンドを次のように追加する。

   - `/volume <volume: float>`: 実行者の `volumeScale` を設定する。
   - `/intonation <intonation: float>`: 実行者の `intonationScale` を設定する。

   ENGINE 0.25.2 の AudioQuery スキーマは両項目を `float` と定義している一方、
   範囲制約を定義していない。そのため本 ADR では根拠のない上限・下限を追加せず、
   値域を製品要件として定める必要が生じた場合は別 ADR で決定する。
3. `VoiceBot` の設定に `user_volumes` と `user_intonations` を追加する。どちらも
   `{Discord user ID: float}` のマップとし、未設定時は `1.0` を使用する。読み込み時に
   キーがない既存設定は空マップとして扱い、保存時は他の個人設定と同様に文字列化した
   ユーザー ID を JSON キーに使用する。
4. メッセージのキュー要素に `volume` と `intonation` を保存する。音声生成時に
   `VoicevoxClient.create_audio()` へ渡し、`/audio_query` の応答に対して
   `volumeScale` と `intonationScale` を設定してから `/synthesis` を呼び出す。
5. ダッシュボードの設定 API と利用者一覧にも 2 項目を追加し、保存済み設定と画面上の
   表示を一致させる。

## Rationale

固定タグは、要求された 0.25.2 を将来の `latest` の更新から切り離す。公開済みの
`nvidia-ubuntu24.04-0.25.2` は、現在の Compose と同じ NVIDIA・amd64 系統であり、
旧 Ubuntu 20.04 の浮動タグを置き換えられる。

音量・抑揚は ENGINE が返す AudioQuery にすでに含まれるため、独自の音声処理を追加
する必要がない。ENGINE は `volumeScale` を波形へ乗算し、`intonationScale` を有声音素の
平均 F0 からの乖離に適用する。クライアントは公式の二段階 API を維持してこの 2 フィールド
だけを更新する。

既存の個人話者・話速と同じ保存単位およびキュー時点のスナップショットを採用すれば、
個人設定の独立性と、再生順待ち中のメッセージの再現性を両立できる。

## Consequences

### Positive

- Compose 起動時の ENGINE は 0.25.2 に固定される。
- `/volume` と `/intonation` は実行者自身の読み上げだけに適用され、再起動後も残る。
- 設定変更後も、すでにキューに入ったメッセージの音量・抑揚は変わらない。
- API で定義済みの AudioQuery を使うため、独自の波形変換を保守しない。

### Negative

- コンテナのベース OS が Ubuntu 20.04 から 24.04 になるため、GPU を使う実行環境での
  起動確認が必要になる。
- `config.json`、ダッシュボード API、テンプレート、テストの更新対象が増える。
- ENGINE の AudioQuery はこの 2 パラメータに数値範囲を公開していないため、値域を
  限定するプロダクト要件が必要になった場合は、別途その根拠とともに決定する必要がある。

### Rejected Alternatives

- **`nvidia-latest`**: 調査時点では 0.25.2 を指すが、将来の更新で実行バージョンが
  変化するため、今回のバージョン指定を満たさない。
- **現行の Ubuntu 20.04 `latest` タグの継続**: 0.25.2 を指定できず、当該タグは
  2025-05-10 更新である。
- **ENGINE プリセット API**: TalkBot2 の既存個人設定モデルと異なり、ユーザー ID を
  直接のキーとして扱えない。既存の JSON 設定を拡張する方が話者・話速と一貫する。
- **サーバー単位の設定**: 個人設定という要求と、既存の `user_speakers` /
  `user_speeds` の保存単位に合わない。

## Implementation and Verification

実装時は次を満たすテストを追加または更新する。

1. Compose のイメージ名が `nvidia-ubuntu24.04-0.25.2` であることを確認する。
2. 起動した ENGINE の `/version` が `0.25.2` を返すことを確認する。
3. `create_audio()` が `/synthesis` に渡す JSON に `speedScale`、`volumeScale`、
   `intonationScale` を含め、指定値が後者 2 フィールドに反映されることを確認する。
4. 両コマンドが実行者の設定だけを更新し、保存・再読み込み後も維持されること、旧形式の
   `config.json` では両マップが空として読み込まれることを確認する。
5. キュー投入後に設定を変えても、投入済み要素が保持する音量・抑揚を使うことを確認する。
6. ダッシュボード API と表示表が新しい 2 項目を返し、未設定値を誤って別の利用者の値と
   して表示しないことを確認する。

## References

- [VOICEVOX ENGINE 0.25.2 release](https://github.com/VOICEVOX/voicevox_engine/releases/tag/0.25.2) — Latest リリース、公開日、リリースタグ。
- [VOICEVOX ENGINE Docker Hub tags](https://hub.docker.com/r/voicevox/voicevox_engine/tags) — `nvidia-ubuntu24.04-0.25.2` の公開状況。
- [0.25.2 AudioQuery model](https://github.com/VOICEVOX/voicevox_engine/blob/0.25.2/voicevox_engine/model.py) — `intonationScale` と `volumeScale` の型・意味。
- [0.25.2 audio query router](https://github.com/VOICEVOX/voicevox_engine/blob/0.25.2/voicevox_engine/app/routers/tts_pipeline.py) — `/audio_query` の初期値が両方 `1` であること。
- [0.25.2 volume processing](https://github.com/VOICEVOX/voicevox_engine/blob/0.25.2/voicevox_engine/tts_pipeline/audio_postprocessing.py) — `volumeScale` の適用方法。
- [0.25.2 intonation processing](https://github.com/VOICEVOX/voicevox_engine/blob/0.25.2/voicevox_engine/tts_pipeline/tts_engine.py) — `intonationScale` の適用方法。
- [Current Compose configuration](../../docker/docker-compose.yml) — 現行 ENGINE イメージ。
- [Current client](../../src/voicevox_client.py) and [bot settings/queue](../../src/bot.py) — 現行の AudioQuery 更新、個人設定、キュー処理。
