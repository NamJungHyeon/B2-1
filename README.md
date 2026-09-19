# 나만의 용돈 기입장 (budget_app)

파일 기반으로 동작하는 콘솔 가계부입니다. 표준 라이브러리만 사용하며 Python 3.10 이상에서 동작합니다.

## 실행 방법

```bash
python3 -m budget_app <command> [options]
python3 -m budget_app --help          # 전체 명령
python3 -m budget_app add --help      # 명령별 도움말
```

테스트:

```bash
python3 -m unittest -v
```

## 저장 파일

기본 저장 폴더는 `./data` 이며 `--data-dir DIR` 로 바꿀 수 있습니다.
처음 실행하면 아래 파일이 자동 생성되고, 카테고리 파일이 비어 있으면
기본 카테고리(`food, transport, rent, salary, etc`)가 채워집니다.

| 파일 | 형식 | 한 줄 예시 |
| --- | --- | --- |
| `data/transactions.jsonl` | JSONL | `{"id": "TX-000001", "type": "expense", "date": "2024-01-15", "amount": 15000, "category": "food", "memo": "점심", "tags": ["meal"]}` |
| `data/categories.jsonl` | JSONL | `{"name": "food"}` |
| `data/budgets.jsonl` | JSONL | `{"month": "2024-01", "amount": 500000}` |
| `data/app.log` | 텍스트 | 명령 실행 로그(소요 시간, 오류) |
| `data/backups/<timestamp>-<unique>/` | 폴더 | `backup` 명령 결과 |

- 백업마다 고유한 폴더를 만들어 같은 초에 실행해도 이전 백업을 덮어쓰지 않습니다.
- 거래 `id`는 `TX-000001` 형태로 순차 발급됩니다.
- update/delete/카테고리 교체처럼 파일 전체를 다시 써야 할 때는 **임시 파일에 쓴 뒤 `os.replace`로 교체**하므로 중간에 중단돼도 원본이 깨지지 않습니다.
- 저장 파일은 제너레이터로 한 줄씩 읽습니다. `list --limit N`은 힙에 N건만 유지하므로 메모리는 N에 비례합니다.
- `search`와 `export`는 최대 1,000건씩 정렬한 임시 JSONL 파일을 두 개씩 병합하고, 결과를 한 건씩 소비합니다. 결과 전체를 메모리에 보관하지 않으며, 동시에 읽는 임시 파일은 최대 2개입니다. 정렬용 디스크 공간은 필요하며 임시 파일은 작업 종료 시 정리합니다.

## 주요 명령

### 거래 추가 (대화형)

```bash
$ python3 -m budget_app add
날짜(YYYY-MM-DD): 2024-01-15
타입(income/expense): expense
카테고리: food
금액(양수): 15000
메모(선택): 점심
태그(쉼표로 구분, 없으면 엔터): meal
[저장 완료] id=TX-000001
```

잘못된 값을 넣으면 오류와 힌트를 보여주고 해당 항목을 다시 묻습니다.
등록되지 않은 카테고리는 거부됩니다 (`category add` 먼저).

### 목록 / 검색

```bash
python3 -m budget_app list --limit 3
python3 -m budget_app search --from 2024-01-01 --to 2024-01-31
python3 -m budget_app search --category food --type expense
python3 -m budget_app search --q 점심 --tag meal
```

출력은 항상 최신순(날짜 → id)입니다.

```
TX-000001 | 2024-01-15 | expense | food      |    15,000 | 점심 #meal
TX-000002 | 2024-01-14 | income  | salary    | 3,000,000 |
```

### 월별 요약 / 예산

```bash
python3 -m budget_app budget set --month 2024-01 --amount 500000
python3 -m budget_app budget show --month 2024-01
python3 -m budget_app summary --month 2024-01 --top 3
```

```
[2024-01 요약] 거래 4건
총 수입: 3,000,000원
총 지출: 185,000원
잔액: 2,815,000원
예산: 100,000원 (사용률 185.0%)
[경고] 예산을 85,000원 초과했습니다!

지출 TOP 3
1) rent 150,000원
2) transport 20,000원
3) food 15,000원
```

데이터가 없는 달도 `2023-05: 데이터 없음`과 수입·지출·잔액 0원을 출력합니다. 예산이 설정되어 있으면 사용률 0.0%도 표시합니다.

### 카테고리 관리

```bash
python3 -m budget_app category list
python3 -m budget_app category add snack          # 이름을 생략하면 대화형으로 묻습니다
python3 -m budget_app category remove snack
python3 -m budget_app category remove food --replace snack   # 사용 중이면 대체 카테고리 필수
```

사용 중인 카테고리를 `--replace` 없이 지우려 하면 거부되고, `--replace`를 주면
해당 거래를 모두 옮긴 뒤 삭제합니다.

### 거래 수정 / 삭제

**update는 옵션 기반(안 A)으로 고정**합니다. 넘긴 옵션만 바뀝니다.

```bash
python3 -m budget_app update --id TX-000001 --amount 17000 --memo "점심(수정)" --tags meal,lunch
python3 -m budget_app delete --id TX-000001
```

없는 id는 `[오류] 존재하지 않는 id입니다: TX-000099` 로 처리되고 exit code 1을 돌려줍니다.

### 가져오기 / 내보내기

```bash
python3 -m budget_app export --out jan.csv --month 2024-01
python3 -m budget_app export --out q1.csv --from 2024-01-01 --to 2024-03-31
python3 -m budget_app import --from jan.csv
```

- `export`는 `--month` 또는 `--from`과 `--to`를 모두 지정해야 합니다. 월과 기간을 함께 지정하면 두 조건의 교집합을 내보냅니다. 겹치는 기간이 없으면 오류로 처리합니다.
- `export`는 임시 파일에 모두 쓴 뒤 교체하므로 실패 시 기존 출력 파일을 보존합니다. 저장 데이터 파일과 `app.log`는 출력 경로로 사용할 수 없습니다.
- `import`는 한 줄씩 검증해 유효한 것만 저장하고, 잘못된 줄은 건너뛰며 이유와 해결 힌트를 출력합니다. 건너뛴 행이 있으면 종료 코드 1을 반환합니다.
- 인코딩·CSV 문법 오류 또는 파일 쓰기 실패로 가져오기가 중단되면 기존 거래 파일을 그대로 보존합니다. 유효한 행들의 저장도 임시 파일 + 원자적 교체로 처리합니다.

```
[완료] imported=2, skipped=2
[오류] 3행: 등록되지 않은 카테고리: ghost
[오류] 4행: 금액은 양수 정수여야 합니다.
[힌트] 표시된 행의 날짜·타입·카테고리·금액을 CSV 스키마에 맞게 수정하세요.
```

#### CSV 스키마 (import/export 공통, UTF-8, 헤더 포함)

| column | required | 설명 |
| --- | --- | --- |
| date | Y | YYYY-MM-DD |
| type | Y | income / expense |
| category | Y | 등록된 카테고리 |
| amount | Y | 양수 정수 |
| memo | N | 문자열 |
| tags | N | 쉼표(,) 구분 문자열 (예: `"meal,lunch"`) |

```csv
date,type,category,amount,memo,tags
2024-01-15,expense,food,15000,점심,"meal,lunch"
2024-01-14,income,salary,3000000,,
```

### 백업

```bash
python3 -m budget_app backup
# [완료] data/backups/20240115-103000-ab12cd34 에 3개 파일 백업
```

## 오류 처리와 종료 코드

손상된 JSONL 문법이나 필드 형식은 파일명과 줄 번호로 안내합니다.

오류는 스택트레이스 대신 `[오류] 원인` + `[힌트] 해결 방법` 형태로 출력합니다.

| 상황 | exit code |
| --- | --- |
| 정상 종료 | 0 |
| 입력값/데이터 오류, 잘못된 UTF-8/CSV, import에서 건너뛴 행 있음 | 1 |
| 파일 처리 오류 (`OSError`) | 2 |
| 잘못된 명령/옵션 (argparse) | 2 |
| Ctrl+C / 입력 중단 | 130 |

## 구조

```
budget_app/
├── __main__.py    # python -m budget_app 진입점
├── cli.py         # argparse, 대화형 입력, 화면 출력
├── services.py    # BudgetService: CRUD/검색/요약/import·export (출력 없음)
├── storage.py     # JsonlFile, TransactionRepository, CategoryStore, BudgetStore (파일 I/O, 원자적 교체)
├── models.py      # Transaction/Budget/Summary dataclass, 입력 검증, AppError
├── sorting.py     # 임시 JSONL 파일을 이용한 스트리밍 외부 병합 정렬
└── decorators.py  # handle_errors(예외 → 메시지+종료코드), log_call(실행 로그·시간 측정)
tests/
├── test_budget_app.py
├── test_regressions.py
├── test_requirements.py
└── test_sorting.py
```

- **모델**: 값의 형태와 검증 규칙만 안다. 파일도 화면도 모른다.
- **저장소**: 파일 하나씩 책임진다. 읽기는 `yield`로 스트리밍, 재작성은 임시 파일 + `os.replace`.
- **서비스**: 저장소를 조합해 기능을 만든다. 결과를 값으로 돌려주고 출력하지 않는다.
- **CLI**: 인자를 파싱해 서비스를 호출하고 결과를 포맷해 출력한다.
- **데코레이터**: `handle_errors`는 CLI 진입점에, `log_call`은 서비스 메서드에 붙어 공통 관심사를 분리한다.

## 과제 요구사항 검증

`python3 -m unittest -v`로 핵심 서비스 동작, 회귀 오류, 실제 CLI 실행,
검색 정렬의 메모리 사용과 임시 파일 정리를 검증합니다.

- 필수 명령: add, list, search, summary, budget set/show, category add/list/remove, update, delete, import/export.
- 모든 명령의 `--help`, 대화형 재입력, 저장 후 재실행, 없는 ID, 예산 초과, 빈 달, 오류 종료 코드를 CLI 테스트로 확인합니다.
- 영구 저장은 JSONL 3개 파일이며 CSV는 가져오기/내보내기 교환 형식입니다.
- 표준 라이브러리만 사용하며 별도 패키지 설치가 필요 없습니다.
- 선택 과제 중 백업, 목록 열 정렬, 저장 원자성은 구현했습니다. 반복 내역 자동 생성은 구현하지 않았습니다.
