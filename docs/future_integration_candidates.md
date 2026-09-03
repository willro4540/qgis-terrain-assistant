# 향후 통합 후보 조사 — GitHub/Hugging Face (2026-09-03)

> 검증 상태: 이 문서의 각 후보는 실제 페이지(GitHub API, Hugging Face 모델카드, 논문 원문)를
> 직접 열어 확인한 내용입니다. 코드는 아직 이 플러그인에 통합되지 않았습니다 — 이 문서는
> "무엇을, 왜, 어떻게 붙일 수 있는지"를 정리한 리서치 기록이며, 인용 출처는 명시적으로
> 표시합니다([[feedback_cite_credible_external_analysis]] 원칙: 공신력 있는 출처가 이미
> 분석한 데이터는 안전판으로 인용하되, 우리가 재현한 것처럼 쓰지 않음).
>
> 근거 등급: (a) 원문 직접 열람 확인 / (b) 검색 스니펫 기반 추론 / (c) 정황상 그럴듯하나
> 미확인 / (d) 미확인.

## 1. TMS for Korea 플러그인 — 국내 베이스맵 타일 소스 (등급 a) — ✅ 구현 완료(2026-09-03)

> **업데이트(2026-09-03)**: 아래 조사를 바탕으로 `datasource.KoreaBasemapSource`로 실제
> 구현했습니다(VWorld 3종 + Naver 3종, 툴바 "Load Korea basemap…"). VWorld 타일과 Naver
> 버전 조회+타일을 직접 `curl`로 찔러 살아있음을 재확인했고, Naver 버전 토큰이 실제로
> 회전한다는 것도 라이브로 확인(참고 플러그인의 하드코딩 폴백 `1778232861` ≠ 방금 조회한
> 실제 버전 `1787907321`). 자세한 내용은 `datasource.py`의 `KoreaBasemapSource` 문서와
> README를 참고. 아래는 원래 조사 기록(그대로 보존).


**출처**: [`mangosystem/qgis-tmsforkorea-plugin`](https://github.com/mangosystem/qgis-tmsforkorea-plugin)
(GPLv2+, 2026-09-03 확인 시점 31★/17 fork/열린 이슈 4건, 배후가 실존 한국 GIS 기업
**MangoSystem** — 스타 수는 적지만 기관 배후로 신뢰도 보강).

**확인된 사실** (저장소 원문 직접 대조):

| 소스 | API 키 | 비고 |
|---|---|---|
| VWorld | 불필요 | 표준/회색/위성/위성+라벨 |
| Naver Maps v5 | 불필요 | 표준/위성/지형/지적 |
| OpenStreetMap | 불필요 | — |
| Azure Maps | 필요(무료 S0 등급) | — |
| Kakao(Daum) | — | **2025-10-20부로 카카오가 타일 직접 접근 차단**(App Key + 공식 JS SDK만 허용) — 플러그인 문제가 아니라 공급자 정책 변경 |
| NGII | **미지원** | 이유: EPSG:5179 비표준 타일 스킴 + GDAL TMS minidriver의 역방향 zoom 미지원이 블로커 |

**이 플러그인과의 연결점**: NGII 미지원 사유(EPSG:5179 비표준 스킴)가 이 저장소 자체의
[`docs/case_study_ngii_data.md`](case_study_ngii_data.md)가 **독립적으로 발견한** "NGII
제품마다 좌표계가 다르고(5186 vs 5179) 도구가 이를 다루기 까다롭다"는 결론과 정확히
일치합니다 — 서로 무관한 두 조사가 같은 결론에 도달한 것으로, 우리 케이스 스터디의
신뢰도를 외부에서 교차검증해주는 셈입니다.

**통합 방식**: 이 플러그인을 의존성으로 끌어오는 게 아니라, VWorld/Naver XYZ 엔드포인트를
직접 호출하는 새 `datasource.py` 클래스(예: `KoreaBasemapSource`)를 `OpenTopographyDemSource`
와 같은 패턴으로 작성 — API 키 없이 국내 베이스맵을 추가할 수 있음.

## 2. Semi-Automatic Classification Plugin (SCP) — 설계 참고용 (등급 a)

**출처**: [`semiautomaticgit/SemiAutomaticClassificationPlugin`](https://github.com/semiautomaticgit/SemiAutomaticClassificationPlugin)
(GPLv3, 171★/58 fork/열린 이슈 27건 — 커뮤니티 활동 자체로 신뢰 확보).

Landsat/Sentinel-2 다운로드 + 지도학습 기반 토지피복 분류를 QGIS 안에서 수행하는 성숙한
구현체("Remotior Sensus" 라이브러리 기반). **의존성으로 가져오지 않고, "이미 로드된
위성영상을 분류하는 기능"을 설계할 때 참고 코드로만 사용.**

## 3. Prithvi-EO-2.0 (IBM/NASA/Jülich) — AI 지형분석, 가장 구체적인 연결점 (등급 a)

**출처**: [`ibm-nasa-geospatial/Prithvi-EO-2.0-300M`](https://huggingface.co/ibm-nasa-geospatial/Prithvi-EO-2.0-300M)
(Apache-2.0, 월 다운로드 17,973회, IBM+NASA+Jülich 공동 개발 — 기관 배후로 신뢰 확보).
아키텍처·성능 수치는 논문 원문([arXiv:2412.02732](https://arxiv.org/html/2412.02732v3))에서
직접 확인.

**아키텍처 요약**: ViT-L(300M)/ViT-H(600M), masked autoencoder(MAE) 방식으로 사전학습 —
입력 패치를 무작위로 가린 뒤 인코더는 안 가려진 패치만 처리하고, 디코더가 원본을 복원하도록
학습(손실은 MSE). 시공간 데이터를 위해 2D 패치/위치 임베딩을 3D로 확장(시간 축 포함),
위도·경도·연도·일자는 1D sin/cos로 별도 인코딩 후 가중합. 학습 데이터는 NASA HLS(Landsat+
Sentinel-2 조화 산출물) 6밴드, 4.2M 샘플(2014-2023).

**가장 중요한 발견 — 산사태 탐지(Landslide4Sense) 태스크**: 파인튜닝 데이터셋이 **"Sentinel-2
멀티스펙트럼 12밴드 + DEM + 경사"**를 입력으로 씁니다(성능: Prithvi-EO-2.0-300M mIoU 71.3%,
논문 인용). 이건 이 플러그인이 **이미 갖고 있는 두 데이터소스(OpenTopography DEM,
Sentinel Hub Sentinel-2)를 그대로 조합**하는 태스크입니다.

**선행 작업 — ✅ 완료(2026-09-03)**: `SentinelHubImagerySource.ALL_BANDS_EVALSCRIPT`로
12밴드 전체(B01/B02/B03/B04/B05/B06/B07/B08/B8A/B09/B11/B12, FLOAT32 반사율)를 받아오도록
확장했습니다. 밴드 목록은 Sentinel Hub 공식 문서(L2A 밴드 목록)에서 직접 확인, evalscript
구조(output.sampleType/다중밴드 반환)도 공식 evalscript v3 문서로 검증했습니다. 툴바
"Load Sentinel-2 imagery (12-band, full spectrum)…", MCP 툴 `load_sentinel_imagery_full_bands`
로 연결. **Prithvi 모델 자체는 아직 미통합** — 이건 그 통합의 선행조건만 치운 것입니다.

**다른 검증된 다운스트림 태스크**(참고용, 전부 논문 원문 인용): 홍수 매핑(Sen1Floods11,
mIoU 90.0~90.3%), 산불흔적 매핑(mIoU 90.5%), 작물 분류(F1 84.4~84.6%).

## 4. Clay Foundation Model v1.5 — 이질적 해상도 대응에 구조적으로 유리 (등급 a)

**출처**: [`Clay-foundation/model`](https://github.com/Clay-foundation/model) (Apache-2.0
코드+가중치, CC-BY-4.0 문서, 612★/105 fork/열린 이슈 40건 — 활발한 커뮤니티).
아키텍처 사양은 [공식 스펙 문서](https://clay-foundation.github.io/model/release-notes/specification.html)
원문 직접 확인.

**아키텍처 요약**: 인코더 311M(dim=1024, depth=24, heads=16) + 디코더 15M, 총 632M
파라미터. **Sentinel-1(2밴드)/Sentinel-2(10)/Landsat(6)/NAIP(4)/LINZ(3)/MODIS(7)를 전부
지원** — 밴드 수·센서가 가변적입니다. 위치 인코딩을 GSD(지상표본거리)로 스케일링해서
**해상도가 다른 데이터를 한 모델에서 다루도록 설계**되어 있습니다.

**이 플러그인과의 연결점**: 이 플러그인은 이미 서로 다른 해상도의 데이터(DEM 30m,
Sentinel-2 10m)를 함께 다루므로, Prithvi(HLS 고정 6밴드)보다 Clay의 가변 해상도/센서
구조가 개념적으로 더 잘 맞습니다. 다만 Clay는 공개된 태스크별 성능 수치가 없어 실제
파인튜닝 전에는 "이 용도에 얼마나 잘 되는지"를 알 수 없습니다 — Prithvi처럼 검증된
안전판 수치를 인용할 수 없는 지점.

## 5. 하드웨어 관련 메모 (배제 사유 아님)

3·4번 모델은 이 프로젝트의 실제 개발 환경(Intel UHD 770 / AMD Radeon Vega 6, 둘 다
내장그래픽)에서 CPU 추론이 될 가능성이 높습니다. **이건 통합 여부를 가르는 기준이
아니라, 통합한 뒤 별도로 최적화할 대상**입니다([[feedback_no_hardware_bias_in_future_expansion_analysis]]).
다만 실무적으로는 이 두 모델이 이 플러그인에 무거운 의존성(`transformers`/`torch`,
Clay 인코더만 1.25GB)을 끌어들이므로, "가벼운 CRS/지도 출력 도구"라는 현재 정체성과
분리해 선택적 모듈로 붙이는 설계가 필요합니다.

## 기각/보류 후보

- **DEM 초해상도 딥러닝 모델**(DSRT, TfaSR, D-SRGAN 등) — 등급 (d). 학술 논문은 실재하나
  Hugging Face 모델카드나 유지되는 공개 저장소를 찾지 못함 — 지금은 통합 불가(하드웨어와
  무관한, 배포된 구현체 부재 문제). 저자가 코드를 공개하면 재검토.
- **Kakao Maps 타일** — 공급자가 2025-10-20부로 직접 접근을 차단해 막다른 길(플러그인
  한계가 아니라 정책 변경).
