# netlify_mtDNA

1. Назначение проекта
------------------------

Проект представляет собой локальный автоматизированный pipeline для подготовки
статического дашборда по данным митохондриальной ДНК (мтДНК) и их предварительной
психиатрической/функциональной интерпретации.

Основная задача проекта:

    исходные файлы данных
            ↓
    локальная нормализация и сверка
            ↓
    формирование sanitized статического HTML-дашборда
            ↓
    pre-deploy security/privacy проверка
            ↓
    подготовка артефакта для Netlify Drop или другого статического хостинга

Проект НЕ является медицинской информационной системой, НЕ ставит диагноз,
НЕ назначает лечение и НЕ должен использоваться как основание для клинических
решений.

Все интерпретации вариантов, включая ACMG/AMP-критерии, класс VUS, психиатрические
ассоциации и функциональные предикторы, носят предварительный научно-аналитический
характер и требуют отдельной кураторской, научной и, при необходимости, юридической
валидации.


2. Ключевой security/privacy принцип
------------------------

В публичный деплой, включая Netlify Drop, должны попадать только данные, которые
явно разрешены к публикации.

Допустимые категории для публичного демо:

    - synthetic data;
    - полностью обезличенные данные;
    - агрегированные данные без возможности реидентификации;
    - sanitized demo data после approval владельца данных, InfoSec и, при
      необходимости, юриста/ответственного за персональные данные.

Недопустимо автоматически публиковать в Netlify Drop:

    - реальные генетические профили, привязанные к человеку;
    - реальные SampleID, если они связаны с субъектом персональных данных;
    - сведения о здоровье, психических расстройствах, предрасположенностях,
      если они могут относиться к специальным категориям персональных данных;
    - сырые VCF/BAM/FASTQ/CRAM-файлы;
    - полные onco/medical/psychiatric профили пациента;
    - API-ключи, токены, пароли, приватные ключи;
    - любые данные, по которым не проведена privacy/legal оценка.

Если исходные данные относятся к реальному человеку, pipeline должен быть
настроен в блокирующий режим:

    classification = real
    contains_personal_data = true
    public_deploy_allowed = false
    allowed_targets = []

В этом случае публичный деплой на Netlify Drop должен быть остановлен до
получения formal approval.

Данный проект не подтверждает соответствие 152-ФЗ, 149-ФЗ, 187-ФЗ или иным
нормативным требованиям автоматически. Любые выводы о правовом статусе данных,
локализации, трансграничной передаче, согласиях, поручении обработки и уведомлении
Роскомнадзора требуют проверки юристом или ответственным за обработку персональных
данных на дату фактического использования.


3. Что делает проект
------------------------

Проект выполняет следующие этапы:

1. Читает исходные файлы:

       data/raw/snps.annotations.txt
       data/raw/samples.qc.txt
       data/curated/from_AMP.csv

2. Нормализует данные:

       - извлекает позиции вариантов;
       - извлекает REF/ALT;
       - распознаёт SampleID;
       - распознаёт гаплогруппу;
       - извлекает QC-сообщения;
       - извлекает Missing Mutations;
       - извлекает Global Private Mutations;
       - распознаёт ALIGN-артефакты;
       - формирует expected AMP positions.

3. Сверяет источники:

       expected_amp_positions = annotation_positions - ALIGN_positions

       Затем сравнивает expected_amp_positions с позициями из from_AMP.csv.

4. Формирует отчёты:

       out/normalized.json
       out/reconciliation_report.json

5. Генерирует sanitized статический дашборд:

       site/index.html
       site/netlify.toml

6. Выполняет pre-deploy проверку:

       out/deployment_report.json

7. Упаковывает артефакт для ручного деплоя:

       dist/mtdna-dashboard.zip


4. Что проект НЕ делает
------------------------

Проект не должен использоваться для следующих целей без отдельной доработки
и approval:

    - обработка реальных персональных данных в публичном контуре;
    - автоматическая публикация чувствительных генетических данных;
    - медицинская диагностика;
    - назначение терапии или дозировок;
    - замена кураторского научного анализа;
    - замена юридической оценки по 152-ФЗ;
    - замена InfoSec-решения о риске;
    - замена процесса incident response при случайной публикации данных;
    - динамический backend с авторизацией, если такая архитектура не реализована
      отдельно.


5. Архитектура проекта
------------------------

5.1. Логическая схема
------------------------

    ┌──────────────────────────────────────────────────────┐
    │ Local trusted processing zone                        │
    │                                                      │
    │ data/raw/snps.annotations.txt                        │
    │ data/raw/samples.qc.txt                              │
    │ data/curated/from_AMP.csv                            │
    │ config/deploy_manifest.json                          │
    │                                                      │
    │                  ↓                                   │
    │ scripts/parse_sources.py                             │
    │                  ↓                                   │
    │ out/normalized.json                                  │
    │ out/reconciliation_report.json                       │
    │                  ↓                                   │
    │ scripts/build_site.py                                │
    │ privacy gate                                         │
    │                  ↓                                   │
    │ site/index.html                                      │
    │ site/netlify.toml                                    │
    │                  ↓                                   │
    │ scripts/predeploy_check.py                           │
    │ security/privacy gate                                │
    │                  ↓                                   │
    │ out/deployment_report.json                           │
    │ dist/mtdna-dashboard.zip                             │
    └──────────────────────────────────────────────────────┘
                           │
                           │ только sanitized/demo/aggregated data
                           ↓
    ┌──────────────────────────────────────────────────────┐
    │ Public static hosting zone                           │
    │                                                      │
    │ Netlify Drop / Netlify CLI / Git-based deploy        │
    │                                                      │
    │ index.html                                           │
    │ netlify.toml                                         │
    └──────────────────────────────────────────────────────┘


5.2. Границы доверия
------------------------

Trusted zone:

    Локальная рабочая станция или защищённый внутренний контур.

    Здесь допустимо обрабатывать:
    - raw .txt;
    - curated .csv;
    - потенциально чувствительные генетические данные;
    - SampleID;
    - гаплогруппу;
    - QC-сообщения;
    - кураторские интерпретации.

Untrusted/public zone:

    Netlify Drop, Netlify CDN, любой публичный URL.

    Здесь допустимо размещать только:
    - synthetic data;
    - aggregated data;
    - sanitized demo data;
    - данные, явно разрешённые к публикации.

Критический контроль между зонами:

    - config/deploy_manifest.json;
    - privacy gate в scripts/build_site.py;
    - security/privacy gate в scripts/predeploy_check.py.


6. Структура проекта
------------------------

Рекомендуемая структура:

    Netlify/
    ├── config/
    │   └── deploy_manifest.json
    │
    ├── data/
    │   ├── raw/
    │   │   ├── snps.annotations.txt
    │   │   └── samples.qc.txt
    │   └── curated/
    │       └── from_AMP.csv
    │
    ├── scripts/
    │   ├── parse_sources.py
    │   ├── build_site.py
    │   ├── predeploy_check.py
    │   └── make_zip.py
    │
    ├── out/
    │   ├── normalized.json
    │   ├── reconciliation_report.json
    │   └── deployment_report.json
    │
    ├── site/
    │   ├── index.html
    │   └── netlify.toml
    │
    ├── dist/
    │   └── mtdna-dashboard.zip
    │
    ├── tests/
    │
    ├── .gitignore
    ├── Makefile
    └── README.txt


7. Входные данные
------------------------

7.1. data/raw/snps.annotations.txt
------------------------

Формат: TSV.

Ожидаемые поля:

    SampleID
    Position
    Ref
    Alt

Назначение:

    Содержит список позиций мтДНК и соответствующих REF/ALT-аллелей для образца.

Пример структуры:

    "SampleID"    "Position"    "Ref"    "Alt"
    "<SAMPLE_ID>"    "250"    "T"    "C"
    "<SAMPLE_ID>"    "410"    "G"    "T"

Важно:

    Файл может содержать чувствительные генетические данные.
    Не размещать в публичной папке site/.
    Не коммитить в открытый репозиторий без privacy review.


7.2. data/raw/samples.qc.txt
------------------------

Формат: TSV.

Ожидаемые поля:

    SampleID
    Haplogroup
    Type
    Message
    Missing Mutations
    Global Private Mutations

Назначение:

    Содержит QC-информацию по образцу:
    - гаплогруппу;
    - ошибки и предупреждения;
    - missing mutations;
    - global private mutations;
    - сообщения об ALIGN-артефактах.

Пример структуры:

    "SampleID"    "Haplogroup"    "Type"    "Message"    "Missing Mutations"    "Global Private Mutations"
    "<SAMPLE_ID>"    "<HAPLOGROUP>"    "error"    "..."    "..."    "..."

Важно:

    Поле Haplogroup может повышать риск реидентификации.
    По умолчанию гаплогруппа не должна отображаться в публичном дашборде.


7.3. data/curated/from_AMP.csv
------------------------

Формат: CSV.

Ожидаемые поля:

    #
    Позиция (р. мтДНК)
    Ген
    Замена
    Тип гена
    Роль в психиатрии
    Популяц. частота (оценка)
    Функц. предиктор (рекомендация)
    Критерии ACMG/AMP (предварит.)
    Класс (предварит.)

Назначение:

    Кураторская таблица вариантов, прошедших предварительный отбор для AMP-анализа.

Важно:

    from_AMP.csv не является полностью автоматическим результатом из двух .txt-файлов.
    Он содержит кураторские аннотации:
    - ген;
    - тип гена;
    - популяционную частоту;
    - функциональный предиктор;
    - ACMG/AMP критерии;
    - предварительный класс;
    - роль в психиатрии.

    Эти поля требуют источника аннотации, версии базы, куратора и approval.


7.4. config/deploy_manifest.json
------------------------

Формат: JSON.

Назначение:

    Machine-readable privacy/security gate.

    Определяет:
    - класс данных;
    - наличие персональных данных;
    - наличие специальных категорий;
    - наличие биометрического контекста;
    - разрешение на публичный деплой;
    - допустимые цели деплоя;
    - sample label для отображения;
    - показывать ли гаплогруппу;
    - ожидаемое количество вариантов;
    - запрещённые строки;
    - лимиты размера Netlify Drop;
    - требование дисклеймера.

Минимальный пример для безопасного демо:

    {
      "dataset_id": "mtdna-psychiatry-demo",
      "version": "0.1.0",
      "classification": "synthetic",
      "contains_personal_data": false,
      "contains_special_category_data": false,
      "contains_biometric_context": false,
      "owner": "research-team",
      "data_approver": "data-owner",
      "security_approver": "infosec-owner",
      "legal_approver": "legal-owner",
      "approval_date": "YYYY-MM-DD",
      "allowed_targets": [
        "netlify-drop-demo"
      ],
      "public_deploy_allowed": true,
      "sample_label": "DEMO-001",
      "show_haplogroup": false,
      "expected_variant_count": 19,
      "prohibited_strings": [
        "<REAL_SAMPLE_ID>",
        "<REAL_HAPLOGROUP>",
        "SampleID",
        "##fileformat=VCF",
        "FASTQ",
        "BAM"
      ],
      "max_site_bytes": 50000000,
      "max_file_bytes": 10000000,
      "max_files": 54000,
      "require_disclaimer": true
    }

Пример блокирующего режима для реальных данных:

    {
      "dataset_id": "mtdna-real-data",
      "version": "0.1.0",
      "classification": "real",
      "contains_personal_data": true,
      "contains_special_category_data": true,
      "contains_biometric_context": false,
      "owner": "research-team",
      "data_approver": "",
      "security_approver": "",
      "legal_approver": "",
      "approval_date": "",
      "allowed_targets": [],
      "public_deploy_allowed": false,
      "sample_label": "INTERNAL",
      "show_haplogroup": false,
      "expected_variant_count": 19,
      "prohibited_strings": [],
      "max_site_bytes": 50000000,
      "max_file_bytes": 10000000,
      "max_files": 54000,
      "require_disclaimer": true
    }

Важно:

    Замените <REAL_SAMPLE_ID> и <REAL_HAPLOGROUP> на фактические значения только
    в локальном конфиге, если они должны блокироваться при проверке.

    Не публикуйте README, манифест или отчёты с реальными идентификаторами
    в открытом репозитории без privacy review.


8. Выходные артефакты
------------------------

8.1. out/normalized.json
------------------------

Содержит нормализованные данные:

    - sample_ids;
    - haplogroups;
    - annotation_positions;
    - annotation_records;
    - align_positions;
    - expected_amp_positions;
    - missing_positions;
    - private_positions;
    - qc_messages;
    - amp_csv_positions;
    - amp_csv_rows.

Назначение:

    Промежуточный машиночитаемый результат парсинга.

Security-примечание:

    Может содержать чувствительные данные.
    Не размещать в site/.
    Не публиковать без sanitization.


8.2. out/reconciliation_report.json
------------------------

Содержит результат сверки:

    - status: PASS или FAIL;
    - issues: критические расхождения;
    - warnings: допустимые или объяснимые расхождения;
    - counts: количество позиций по источникам.

Назначение:

    Показывает, согласуются ли:
    - snps.annotations.txt;
    - samples.qc.txt;
    - from_AMP.csv.

Логика статусов:

    PASS  — критические issues отсутствуют.
    FAIL  — есть критические issues, публичный деплой должен быть остановлен.
    warnings — не блокируют pipeline по умолчанию, но требуют review.


8.3. site/index.html
------------------------

Статический sanitized дашборд.

Содержит:

    - заголовок;
    - демо/privacy banner;
    - карточки метрик;
    - панель образца и QC;
    - таблицу вариантов;
    - условный приоритет визуализации;
    - методологию;
    - дисклеймер;
    - дату сборки;
    - dataset_id и version из манифеста.

Важно:

    Это единственный основной файл, который предназначен для публичного деплоя.

    В нём не должно быть:
    - реальных SampleID;
    - реальных гаплогрупп, если show_haplogroup=false;
    - raw VCF/BAM/FASTQ;
    - API-ключей;
    - токенов;
    - паролей;
    - медицинских рекомендаций по лечению.


8.4. site/netlify.toml
------------------------

Конфигурация Netlify для статического деплоя.

Может содержать:

    - security headers;
    - CSP;
    - X-Content-Type-Options;
    - X-Frame-Options;
    - Referrer-Policy;
    - Permissions-Policy;
    - SPA redirect, если используется SPA-роутинг.

Пример безопасных headers для статического HTML без JavaScript:

    [[headers]]
      for = "/*"
      [headers.values]
        X-Content-Type-Options = "nosniff"
        X-Frame-Options = "DENY"
        Referrer-Policy = "no-referrer"
        Permissions-Policy = "camera=(), microphone=(), geolocation=()"
        Content-Security-Policy = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'; object-src 'none'"

Важно:

    Не использовать wildcard CORS:

        Access-Control-Allow-Origin = "*"

    если это не обосновано и не одобрено InfoSec.


8.5. out/deployment_report.json
------------------------

Отчёт pre-deploy проверки.

Содержит:

    - status: PASS или FAIL;
    - target;
    - dataset_id;
    - version;
    - classification;
    - errors;
    - warnings;
    - file_hashes_sha256;
    - file_count;
    - total_bytes.

Назначение:

    Доказательный артефакт для approval и аудита.


8.6. dist/mtdna-dashboard.zip
------------------------

ZIP-архив папки site/.

Назначение:

    Удобный артефакт для ручного перетаскивания в Netlify Drop или передачи
    ответственному за деплой.


9. Скрипты проекта
------------------------

9.1. scripts/parse_sources.py
------------------------

Назначение:

    Читает исходные файлы, нормализует данные и выполняет сверку.

Основные функции:

    - автоопределение корня проекта;
    - чтение TSV;
    - чтение CSV;
    - извлечение позиций;
    - извлечение ALIGN-артефактов;
    - извлечение Missing Mutations;
    - извлечение Global Private Mutations;
    - формирование expected_amp_positions;
    - сверка с from_AMP.csv;
    - запись out/normalized.json;
    - запись out/reconciliation_report.json.

Ключевая логика:

    expected_amp_positions = annotation_positions - ALIGN_positions

Особенности сверки:

    - ALIGN-позиции ожидаемо присутствуют в Global Private Mutations, но исключаются
      из expected AMP set;
    - кураторская позиция может отсутствовать в Global Private Mutations;
      в этом случае формируется warning, а не критическая ошибка;
    - если from_AMP.csv не совпадает с expected_amp_positions по составу,
      формируется issue.

Запуск:

    python3 scripts/parse_sources.py


9.2. scripts/build_site.py
------------------------

Назначение:

    Генерирует sanitized статический дашборд.

Основные функции:

    - читает config/deploy_manifest.json;
    - выполняет privacy gate;
    - читает out/normalized.json;
    - читает data/curated/from_AMP.csv;
    - создаёт site/index.html;
    - создаёт site/netlify.toml;
    - маскирует SampleID через sample_label;
    - скрывает гаплогруппу, если show_haplogroup=false;
    - добавляет обязательный дисклеймер.

Privacy gate:

    Сборка для публичного target блокируется, если:

    - classification = real;
    - contains_personal_data = true;
    - contains_special_category_data = true;
    - contains_biometric_context = true;
    - public_deploy_allowed = false;
    - target отсутствует в allowed_targets;
    - для sanitized/aggregated/derived данных отсутствуют required approvers.

Запуск:

    python3 scripts/build_site.py


9.3. scripts/predeploy_check.py
------------------------

Назначение:

    Выполняет security/privacy проверку перед деплоем.

Проверяет:

    - наличие site/index.html;
    - отсутствие raw-файлов в site/;
    - допустимые расширения файлов;
    - размер папки site/;
    - размер отдельных файлов;
    - количество файлов;
    - отсутствие запрещённых строк;
    - отсутствие возможных секретов;
    - наличие обязательного дисклеймера;
    - соответствие deploy_manifest.json;
    - допустимость цели деплоя.

Блокирующие условия:

    - site/index.html отсутствует;
    - в site/ найдены .txt, .csv, .vcf, .bam, .fastq и другие raw-расширения;
    - найдены prohibited_strings;
    - найдены secret patterns;
    - превышены лимиты размера;
    - public_deploy_allowed=false;
    - classification=real;
    - contains_personal_data=true;
    - contains_special_category_data=true;
    - contains_biometric_context=true;
    - target не разрешён;
    - отсутствуют required approvals для sanitized data;
    - отсутствует обязательный дисклеймер.

Запуск:

    python3 scripts/predeploy_check.py


9.4. scripts/make_zip.py
------------------------

Назначение:

    Упаковывает site/ в dist/mtdna-dashboard.zip.

Запуск:

    python3 scripts/make_zip.py


10. Быстрый запуск
------------------------

10.1. Перейти в проект
------------------------

    cd /path/to/Netlify

Пример:

    cd /home/user/Desktop/Netlify


10.2. Создать структуру
------------------------

    mkdir -p config data/raw data/curated scripts out site dist tests


10.3. Разместить исходные файлы
------------------------

Положить файлы:

    data/raw/snps.annotations.txt
    data/raw/samples.qc.txt
    data/curated/from_AMP.csv


10.4. Создать или отредактировать манифест
------------------------

Файл:

    config/deploy_manifest.json

Перед запуском обязательно проверить:

    - classification;
    - contains_personal_data;
    - contains_special_category_data;
    - contains_biometric_context;
    - public_deploy_allowed;
    - allowed_targets;
    - sample_label;
    - show_haplogroup;
    - prohibited_strings;
    - expected_variant_count.


10.5. Запустить парсинг и сверку
------------------------

    python3 scripts/parse_sources.py

Ожидаемый результат:

    Normalized: out/normalized.json
    Reconciliation: out/reconciliation_report.json
    Status: PASS

Если Status: FAIL:

    - открыть out/reconciliation_report.json;
    - прочитать issues;
    - не продолжать публичный деплой до устранения или обоснования расхождений.


10.6. Сгенерировать дашборд
------------------------

    python3 scripts/build_site.py

Ожидаемый результат:

    Created: site/index.html
    Created: site/netlify.toml
    Rows: <number>

Если сборка заблокирована privacy gate:

    - проверить config/deploy_manifest.json;
    - убедиться, что данные действительно synthetic/sanitized/aggregated;
    - получить required approvals;
    - не обходить блокировку без formal risk acceptance.


10.7. Выполнить pre-deploy проверку
------------------------

    python3 scripts/predeploy_check.py

Ожидаемый результат:

    Deployment report: out/deployment_report.json
    Status: PASS

Если Status: FAIL:

    - открыть out/deployment_report.json;
    - устранить errors;
    - повторить проверку.


10.8. Создать ZIP
------------------------

    python3 scripts/make_zip.py

Результат:

    dist/mtdna-dashboard.zip


10.9. Локальный просмотр
------------------------

    python3 -m http.server 8080 --directory site

Открыть в браузере:

    http://localhost:8080

Остановить сервер:

    Ctrl+C


11. Деплой в Netlify Drop
------------------------

11.1. Ограничения Netlify Drop
------------------------

Согласно предоставленному руководству:

    - Netlify Drop публикует статические сайты через перетаскивание папки или ZIP;
    - в корне публичной директории должен быть index.html;
    - в анонимном режиме файлы публикуются как есть, без сборки;
    - рекомендуемый размер папки — до 50 МБ;
    - отдельные файлы более 10 МБ могут вызывать проблемы;
    - количество файлов в директории — до 54 000;
    - анонимный сайт живёт примерно до 1 часа;
    - для постоянного сайта нужно создать аккаунт Netlify и "заявить" сайт;
    - для SPA нужно правило:

        [[redirects]]
          from = "/*"
          to = "/index.html"
          status = 200

    - для динамики лучше использовать Netlify Functions;
    - API-ключи нельзя хранить во фронтенде;
    - wildcard CORS признан небезопасным.


11.2. Ручной деплой через Netlify Drop
------------------------

1. Убедиться, что:

       python3 scripts/predeploy_check.py

   вернул Status: PASS.

2. Открыть:

       https://app.netlify.com/drop

3. Перетащить папку:

       site/

   или архив:

       dist/mtdna-dashboard.zip

   если интерфейс принимает archive.

4. Дождаться публикации.

5. Получить URL вида:

       https://<random-string>.netlify.app

6. Открыть URL и проверить:

       - дашборд отображается;
       - нет реальных SampleID;
       - нет реальной гаплогруппы, если она не разрешена;
       - нет raw-файлов;
       - нет API-ключей;
       - есть дисклеймер;
       - нет внешних незапланированных запросов.

7. При необходимости "заявить" сайт в аккаунте Netlify.

Важно:

    Постоянный публичный URL увеличивает exposure risk.
    Для чувствительных данных постоянный публичный деплой не рекомендуется
    без formal approval.


11.3. Автоматизация деплоя
------------------------

Netlify Drop как drag-and-drop интерфейс полностью не автоматизируется официально.

Для автоматизации нужно использовать:

    - Netlify CLI;
    - Netlify API;
    - Git integration;
    - CI/CD pipeline.

Пример через Netlify CLI:

    npx netlify deploy --dir=site --prod

Требуется:

    NETLIFY_AUTH_TOKEN
    NETLIFY_SITE_ID

Важно:

    Секреты должны храниться только в protected CI secret storage.
    Нельзя хранить NETLIFY_AUTH_TOKEN в репозитории, логах, README или клиентском коде.

Для production deploy рекомендуется использовать environment approval, например
GitHub Actions environment protection.


12. Security/privacy модель
------------------------

12.1. Активы
------------------------

| Актив | Описание | Предварительная критичность |
|---|---|---|
| snps.annotations.txt | позиции и аллели образца | высокая |
| samples.qc.txt | QC, гаплогруппа, private/missing mutations | высокая |
| from_AMP.csv | кураторские интерпретации | средняя/высокая |
| deploy_manifest.json | privacy/security gate | высокая |
| out/normalized.json | нормализованные данные | высокая |
| out/reconciliation_report.json | отчёт сверки | средняя |
| site/index.html | публичный артефакт | зависит от данных |
| site/netlify.toml | конфигурация хостинга | средняя |
| out/deployment_report.json | доказательство проверки | средняя |
| dist/mtdna-dashboard.zip | деплой-артефакт | зависит от содержимого |
| Netlify URL | публичная экспозиция | высокая при чувствительных данных |


12.2. Угрозы
------------------------

| ID | Угроза | Описание |
|---|---|---|
| T1 | Неавторизованное раскрытие данных | Публичный URL доступен любому посетителю |
| T2 | Реидентификация | SampleID + гаплогруппа + редкие варианты могут позволить связать данные с человеком |
| T3 | Нарушение требований к ПДн | Реальные ПДн обрабатываются/публикуются без правового основания, локализации или трансграничной оценки |
| T4 | Ошибочная публикация raw data | В site/ случайно попадают .txt, .csv, .vcf, .bam, .fastq |
| T5 | Утечка секретов | API-ключи, токены, пароли попадают в HTML, TOML, ZIP или репозиторий |
| T6 | Ложномедицинское восприятие | Пользователь принимает VUS и психиатрические ассоциации за диагноз или рекомендацию |
| T7 | Supply-chain риск | Вредоносные или уязвимые зависимости при добавлении frontend-фреймворка |
| T8 | Отсутствие аудита | Невозможно восстановить, кто, когда и какие данные опубликовал |
| T9 | Превышение лимитов Netlify Free | Сайт становится недоступен из-за трафика, сборок или функций |
| T10 | Инцидент при случайном деплое | Реальные данные опубликованы, требуется containment и possible notification |


12.3. Risk register
------------------------

| ID | Риск | Likelihood | Impact | Risk | Мера |
|---|---|---|---|---|---|
| R1 | Публикация реального генетического образца в Netlify Drop | High, если данные реальные | Critical | Critical | deploy_manifest блокирует public deploy |
| R2 | Раскрытие SampleID в HTML | Medium/High | High | High | sample_label, prohibited_strings scan |
| R3 | Раскрытие гаплогруппы | Medium | High | High | show_haplogroup=false по умолчанию |
| R4 | Нарушение требований к ПДн/локализации | Medium/High | High | High | privacy/legal review, не использовать public Netlify для ПДн без approval |
| R5 | Raw .txt/.csv/.vcf попали в site/ | Medium | High | High | allowlist, extension scan, predeploy_check |
| R6 | Секреты в артефакте | Medium | High | High | secret patterns scan, CI secrets |
| R7 | Ложная медицинская интерпретация | Medium | Medium/High | Medium/High | дисклеймер, кураторский approval |
| R8 | Расхождение данных между источниками | High по исходным файлам | Medium | Medium | reconciliation report, issues/warnings |
| R9 | Превышение лимитов Netlify Free | Low для одного HTML | Medium | Low/Medium | size checks, monitoring |
| R10 | Supply-chain риск | Low/Medium | Medium | Medium | минимальные зависимости, lockfiles, SCA |
| R11 | Автоматический деплой без человека | Medium | High | High | environment approval, manual Drop для демо |
| R12 | Отсутствие доказательств деплоя | Medium | Medium | Medium | deployment_report.json, SHA-256 hashes |


13. Privacy / 152-ФЗ: предварительные соображения
------------------------

Важно:

    Ниже приведён предварительный анализ. Он не является юридическим заключением.
    Требуется проверка актуальных редакций норм и фактической архитектуры
    юристом или ответственным за обработку персональных данных.

13.1. Могут ли данные быть персональными
------------------------

Генетические данные, привязанные к образцу, могут относиться к персональным данным,
если:

    - данные относятся к идентифицированному или идентифицируемому физическому лицу;
    - SampleID связан с человеком;
    - есть привязка к медицинской карте;
    - данные могут использоваться для идентификации;
    - данные касаются здоровья или предрасположенностей;
    - существует риск реидентификации.

Особую осторожность требуют случаи, когда данные включают:

    - сведения о психическом здоровье;
    - сведения о заболеваниях;
    - сведения о предрасположенностях;
    - данные родственников;
    - биометрический контекст;
    - медицинские рекомендации.

Предварительно такие данные могут относиться к специальным категориям персональных
данных, связанных со здоровьем. Точная квалификация зависит от цели обработки,
контекста и применимых норм.


13.2. Netlify как зарубежная инфраструктура
------------------------

Netlify — зарубежная платформа. Если реальные персональные данные обрабатываются,
хранятся, передаются или публикуются через Netlify, необходимо отдельно проверять:

    - локализацию баз при сборе ПДн граждан РФ через Интернет;
    - трансграничную передачу;
    - договор поручения обработки, если применимо;
    - меры защиты у обработчика;
    - правовое основание обработки;
    - согласие, если оно используется;
    - уведомление Роскомнадзора, если требуется;
    - фактические процессы записи, хранения, обработки и резервного копирования;
    - используемые subprocessors.

Нельзя делать вывод о допустимости только по названию сервиса или стране
регистрации поставщика.


13.3. Инцидент с ПДн
------------------------

Если случайно опубликованы реальные персональные данные, это может быть инцидентом.

Предварительный порядок действий:

1. Немедленно зафиксировать:
       - URL;
       - время обнаружения;
       - deployment ID;
       - состав файлов;
       - хэши артефактов;
       - CI/локальные логи;
       - скриншоты;
       - кто имел доступ.

2. Ограничить развитие ущерба:
       - удалить или отключить публичный сайт через Netlify dashboard/API,
         если это предусмотрено процедурой;
       - не уничтожать доказательства до фиксации.

3. Определить:
       - были ли ПДн;
       - категории субъектов;
       - состав ПДн;
       - объём;
       - возможные получатели;
       - признак специальной категории;
       - признак биометрического контекста.

4. Назначить ответственного.

5. Провести внутреннее расследование.

6. Проверить обязанность уведомления уполномоченного органа.

   По baseline препромпта при инциденте с ПДн ориентировочно:
       - первичное уведомление — в течение 24 часов;
       - результаты внутреннего расследования — в течение 72 часов.

  Normu и порядок нужно перепроверить на дату фактического события.

7. Обновить контроли:
       - ужесточить deploy_manifest;
       - включить human approval;
       - добавить DLP/pre-deploy scan;
       - запретить public target для real data;
       - провести lessons learned.


14. Acceptance criteria
------------------------

Деплой можно считать приемлемым только если выполнены все условия:

    [ ] config/deploy_manifest.json существует и валиден.
    [ ] classification корректно отражает тип данных.
    [ ] contains_personal_data, contains_special_category_data,
        contains_biometric_context заполнены честно.
    [ ] public_deploy_allowed соответствует решению владельца данных/InfoSec/legal.
    [ ] allowed_targets содержит фактическую цель деплоя.
    [ ] data_approver, security_approver, legal_approver заполнены, если требуется.
    [ ] python3 scripts/parse_sources.py завершён.
    [ ] out/reconciliation_report.json имеет status PASS или обоснованные warnings.
    [ ] python3 scripts/build_site.py завершён без privacy gate error.
    [ ] site/index.html существует.
    [ ] site/netlify.toml существует.
    [ ] В site/ нет .txt, .csv, .vcf, .bam, .fastq, .gz, .zip, .tar.
    [ ] В site/ нет API-ключей, токенов, паролей, приватных ключей.
    [ ] В HTML нет prohibited_strings.
    [ ] В HTML есть обязательный дисклеймер.
    [ ] python3 scripts/predeploy_check.py вернул status PASS.
    [ ] out/deployment_report.json сохранён.
    [ ] Размер site/ не превышает configured limits.
    [ ] Отдельные файлы не превышают configured limits.
    [ ] Количество файлов не превышает configured limits.
    [ ] Локальный preview проверен.
    [ ] Публичный URL после деплоя проверен вручную.
    [ ] Владелец данных, InfoSec и при необходимости юрист согласовали публикацию.


15. Известные особенности сверки данных
------------------------

15.1. ALIGN-артефакты
------------------------

Позиции, помеченные в samples.qc.txt как ALIGN, исключаются из expected AMP set.

Пример логики:

    expected_amp_positions = annotation_positions - ALIGN_positions

При этом ALIGN-позиции могут оставаться в Global Private Mutations.
Это ожидаемо и не должно считаться критической ошибкой, если скрипт корректно
исключает их из сравнения.


15.2. Кураторские позиции вне Global Private Mutations
------------------------

Позиция может присутствовать в from_AMP.csv, но отсутствовать в Global Private Mutations.

Возможные причины:

    - позиция известна Phylotree для конкретной гаплогруппы;
    - QC-логика обрабатывает D-loop отдельно;
    - позиция добавлена куратором дополнительно;
    - кураторская аннотация использует иной источник или иную логику.

Такой случай должен формировать warning, а не блокирующий issue, если куратор
явно подтвердил включение позиции.


15.3. Расхождение количества позиций
------------------------

Если количество expected_amp_positions не совпадает с количеством позиций
в from_AMP.csv, это критическое расхождение.

Необходимо проверить:

    - корректность парсинга TSV;
    - корректность распознавания ALIGN;
    - наличие дубликатов;
    - пропущенные строки;
    - кодировку файлов;
    - разделители;
    - кавычки;
    - соответствие кураторской таблицы исходным данным.


16. Troubleshooting
------------------------

16.1. FileNotFoundError: File not found .../snps.annotations.txt
------------------------

Симптом:

    FileNotFoundError: File not found:
    /home/user/Desktop/data/raw/snps.annotations.txt

Причина:

    Скрипт ищет файлы не в той папке, где они реально лежат.

Решение:

    Вариант A: привести проект к структуре:

        Netlify/
        ├── scripts/
        │   └── parse_sources.py
        ├── data/
        │   ├── raw/
        │   │   ├── snps.annotations.txt
        │   │   └── samples.qc.txt
        │   └── curated/
        │       └── from_AMP.csv

    Затем запускать из корня:

        python3 scripts/parse_sources.py

    Вариант B: если файлы лежат плоско рядом со скриптом, использовать
    автоопределение root или изменить пути в скрипте:

        ROOT = Path(__file__).resolve().parent
        RAW_DIR = ROOT
        CURATED_DIR = ROOT
        OUT_DIR = ROOT / "out"


16.2. SyntaxError: unmatched ')'
------------------------

Симптом:

    if not any phrase in text for phrase in required_phrases):
                                                           ^
    SyntaxError: unmatched ')'

Причина:

    Пропущена открывающая скобка после any.

Неправильно:

    if not any phrase in text for phrase in required_phrases):

Правильно:

    if not any(phrase in text for phrase in required_phrases):


16.3. FileNotFoundError: Missing required file .../deploy_manifest.json
------------------------

Симптом:

    FileNotFoundError: Missing required file:
    /home/user/Desktop/Netlify/config/deploy_manifest.json

Причина:

    Не создан файл манифеста.

Решение:

    Создать:

        mkdir -p config

    и поместить валидный JSON в:

        config/deploy_manifest.json


16.4. Status: FAIL в reconciliation_report.json
------------------------

Симптом:

    Status: FAIL
     - Global private mutation позиции не входят в expected AMP set: ...
     - Expected AMP позиции не найдены в Global Private Mutations: ...

Действия:

    1. Открыть:

           cat out/reconciliation_report.json

    2. Проверить, являются ли расхождения:
       - ожидаемыми ALIGN-исключениями;
       - кураторскими позициями;
       - реальными ошибками данных.

    3. Если это ALIGN-артефакты, убедиться, что parse_sources.py исключает
       align_positions из сравнения private_not_expected.

    4. Если это кураторская позиция, перевести её в warnings после review.

    5. Если расхождение реальное, не продолжать деплой до исправления данных.


16.5. predeploy_check.py вернул FAIL
------------------------

Действия:

    1. Открыть:

           cat out/deployment_report.json

    2. Найти errors.

    3. Устранить причины:
       - удалить raw-файлы из site/;
       - удалить prohibited strings;
       - удалить секреты;
       - уменьшить размер;
       - добавить дисклеймер;
       - исправить deploy_manifest.json.

    4. Повторить:

           python3 scripts/build_site.py
           python3 scripts/predeploy_check.py


16.6. Дашборд не открывается после Netlify Drop
------------------------

Проверить:

    - в перетаскиваемой папке есть index.html;
    - папка перетаскивается целиком, а не отдельный файл;
    - нет ошибки 404 из-за неправильной структуры;
    - для SPA есть redirect:

        [[redirects]]
          from = "/*"
          to = "/index.html"
          status = 200

    - нет превышения лимитов размера;
    - анонимный сайт не истёк примерно через 1 час.


17. Makefile
------------------------

Пример Makefile:

    PYTHON ?= python3
    TARGET ?= netlify-drop-demo

    .PHONY: clean parse build check preview zip all deploy-cli

    clean:
        rm -rf site dist out

    parse:
        $(PYTHON) scripts/parse_sources.py

    build:
        DEPLOY_TARGET=$(TARGET) $(PYTHON) scripts/build_site.py

    check:
        DEPLOY_TARGET=$(TARGET) $(PYTHON) scripts/predeploy_check.py

    preview:
        $(PYTHON) -m http.server 8080 --directory site

    zip:
        $(PYTHON) scripts/make_zip.py

    all: clean parse build check zip

    deploy-cli:
        DEPLOY_TARGET=$(TARGET) $(PYTHON) scripts/parse_sources.py
        DEPLOY_TARGET=$(TARGET) $(PYTHON) scripts/build_site.py
        DEPLOY_TARGET=$(TARGET) $(PYTHON) scripts/predeploy_check.py
        npx netlify deploy --dir=site --prod --site=$(NETLIFY_SITE_ID)

Использование:

    make all

Для локального просмотра:

    make preview

Для CLI deploy только после approval:

    export NETLIFY_AUTH_TOKEN="..."
    export NETLIFY_SITE_ID="..."
    make deploy-cli

Важно:

    Не хранить NETLIFY_AUTH_TOKEN и NETLIFY_SITE_ID в репозитории.


18. CI/CD
------------------------

18.1. Безопасный вариант для демо
------------------------

CI автоматически:

    - парсит данные;
    - собирает site/;
    - выполняет pre-deploy check;
    - создаёт ZIP artifact.

Человек вручную:

    - скачивает artifact;
    - проверяет deployment_report.json;
    - перетаскивает site/ или ZIP в Netlify Drop.

Это снижает риск автоматической публикации нежелательных данных.


18.2. Полный автоматический деплой
------------------------

Возможен через:

    - GitHub Actions;
    - GitLab CI;
    - Netlify CLI;
    - Netlify API;
    - Git integration.

Обязательные условия:

    - repository содержит только synthetic/sanitized данные;
    - deploy_manifest.json разрешает target;
    - production environment защищён approval;
    - секреты хранятся в CI secret storage;
    - pre-deploy check является блокирующим;
    - есть rollback/deletion plan;
    - есть audit trail.


19. Ограничения проекта
------------------------

19.1. Технические ограничения
------------------------

    - Проект генерирует статический HTML, а не полноценное SPA с backend.
    - Netlify Drop не запускает Python.
    - Netlify Drop не читает локальные .txt/.csv на сервере.
    - Netlify Drop не выполняет bioinformatics-обработку "на лету".
    - Drag-and-drop деплой не полностью автоматизируется официально.
    - Анонимный сайт живёт примерно до 1 часа.
    - Бесплатный тариф Netlify имеет лимиты трафика, сборок, функций и деплоев.


19.2. Научные/медицинские ограничения
------------------------

    - from_AMP.csv содержит кураторские интерпретации.
    - ACMG/AMP классы являются предварительными.
    - VUS не означает диагноз.
    - Психиатрические ассоциации не являются индивидуальным прогнозом.
    - Дашборд не заменяет врача, генетика, психиатра или лабораторную диагностику.
    - Любые рекомендации по дозировкам, если они появятся, требуют отдельной
      медицинской и юридической валидации.


19.3. Privacy/legal ограничения
------------------------

    - Проект не определяет автоматически, являются ли данные ПДн.
    - Проект не проверяет фактическую локализацию基础设施 Netlify.
    - Проект не заменяет DPA, legal review или уведомление Роскомнадзора.
    - Проект не подтверждает соответствие 152-ФЗ.
    - Проект не принимает risk acceptance от имени организации.


20. Residual risk
------------------------

Даже после прохождения pipeline остаются остаточные риски:

    1. Human error
       Разработчик может вручную положить реальный файл в site/ или изменить
       deploy_manifest.json без approval.

    2. Re-identification
       Агрегированные или обезличенные генетические данные иногда можно связать
       с человеком через внешние базы, родственные связи, фенотип или медицинские данные.

    3. Medical misinterpretation
       Пользователь может принять демо-интерпретацию за клинический вывод.

    4. Availability
       Netlify Free может ограничить доступность при превышении лимитов.

    5. Supply chain
       При добавлении frontend-зависимостей появляются npm/pip риски.

    6. Persistence
       После claim сайта в аккаунте Netlify удаление может потребовать отдельных
       действий и не всегда означает немедленное уничтожение всех копий/кэшей.

    7. Legal uncertainty
       Статус ПДн, специальных категорий, биометрического контекста, локализации
       и трансграничной передачи требует юридической проверки.

Снижение residual risk:

    - automated pre-deploy scans;
    - synthetic data only для публичных демо;
    - mandatory human approval;
    - deployment_report.json;
    - SHA-256 artifact hashes;
    - documented deletion process;
    - medical disclaimer;
    - dependency management;
    - periodic privacy/legal review.


21. Рекомендуемый режим использования
------------------------

21.1. Для реальных данных
------------------------

Рекомендуется:

    - не использовать Netlify Drop;
    - обрабатывать данные локально или во внутреннем защищённом контуре;
    - использовать deploy_manifest с public_deploy_allowed=false;
    - применять authN/authZ, audit logging, encryption, DLP, retention/deletion policy;
    - провести privacy/legal assessment.

21.2. Для публичного демо
------------------------

Допускается:

    - использовать только synthetic/sanitized/aggregated данные;
    - получить approval владельца данных, InfoSec и при необходимости юриста;
    - запустить полный pipeline;
    - проверить deployment_report.json;
    - вручную проверить публичный URL;
    - использовать анонимный Drop для разовой демонстрации;
    - не claim сайт, если нет необходимости.

21.3. Для регулярного демо
------------------------

Рекомендуется:

    - Git repository только с synthetic данными;
    - CI pipeline;
    - blocking pre-deploy checks;
    - environment approval;
    - Netlify CLI/API или Git integration;
    - мониторинг лимитов;
    - план удаления/обновления.


22. Чек-лист перед публикацией
------------------------

    [ ] Я确定, что данные synthetic/sanitized/aggregated или имею approval.
    [ ] deploy_manifest.json не содержит real/PD flags для публичного target.
    [ ] sample_label не раскрывает реальный SampleID.
    [ ] show_haplogroup=false, если гаплогруппа не разрешена.
    [ ] prohibited_strings содержат реальные идентификаторы, которые нельзя публиковать.
    [ ] parse_sources.py выполнен.
    [ ] reconciliation_report.json проверен.
    [ ] build_site.py выполнен.
    [ ] site/ содержит только index.html и netlify.toml, если используется строгий режим.
    [ ] predeploy_check.py выполнен.
    [ ] deployment_report.json имеет status PASS.
    [ ] Локальный preview проверен.
    [ ] Нет raw .txt/.csv/.vcf/.bam/.fastq в публичной папке.
    [ ] Нет секретов.
    [ ] Есть дисклеймер.
    [ ] Публичный URL проверен после деплоя.
    [ ] Владелец данных/InfoSec/legal согласовали публикацию, если требуется.


23. Примеры команд для проверки
------------------------

Проверить структуру:

    find . -maxdepth 3 -type f | sort

Проверить размер site/:

    du -sh site/

Найти файлы больше 10 МБ:

    find site/ -type f -size +10M

Посчитать файлы:

    find site/ -type f | wc -l

Проверить отсутствие raw-расширений:

    find site/ -type f \( -name "*.txt" -o -name "*.csv" -o -name "*.vcf" -o -name "*.bam" -o -name "*.fastq" \) -print

Проверить prohibited strings вручную:

    grep -R -I -n "<REAL_SAMPLE_ID>" site/ || echo "Чисто"
    grep -R -I -n "<REAL_HAPLOGROUP>" site/ || echo "Чисто"
    grep -R -I -n "SampleID" site/ || echo "Чисто"
    grep -R -I -n "##fileformat=VCF" site/ || echo "Чисто"

Проверить возможные секреты:

    grep -R -I -n -E "(api[_-]?key|apikey|secret|token|password|passwd|pwd)" site/ || echo "Чисто"

Посмотреть отчёт сверки:

    cat out/reconciliation_report.json

Посмотреть deployment report:

    cat out/deployment_report.json


24. Версии и совместимость
------------------------

Требуется:

    - Python 3.10+ рекомендуется;
    - стандартная библиотека Python: csv, json, re, pathlib, html, hashlib, zipfile;
    - опционально: zip CLI;
    - опционально: Node.js/npx только при использовании Netlify CLI.

Проект не требует внешних Python-зависимостей в базовой версии.


25. Лицензия
------------------------

Лицензия не определена.

Если проект внутренний, рекомендуется указать:

    Internal use only. Not for redistribution without approval.

Если проект открытый, нужно отдельно выбрать лицензию и провести review
на наличие чувствительных данных, медицинских интерпретаций и третьих источников.


26. Владелец и контакты
------------------------

Заполнить при использовании:

    Owner:
    Data owner:
    Security approver:
    Legal approver:
    Maintainer:
    Incident contact:
    Repository:
    Deployment target:


27. История изменений
------------------------

Формат:

    YYYY-MM-DD
    - изменение;
    - причина;
    - affected scripts;
    - affected data classification;
    - approval reference.

Пример:

    2026-09-26
    - Добавлен автоопределитель корня проекта в parse_sources.py.
    - ALIGN-позиции исключены из critical private mismatch.
    - Кураторские позиции вне Global Private Mutations переведены в warnings.
    - Добавлен deploy_manifest.json как privacy gate.
    - Исправлен syntax error в predeploy_check.py.
    - Добавлен README.txt с security/privacy моделью.


28. Финальный disclaimer
------------------------

Дашборд и все связанные отчёты носят информационно-аналитический характер.

Они:

    - не являются медицинским заключением;
    - не являются диагнозом;
    - не являются рекомендацией по лечению;
    - не заменяют консультацию врача, генетика или психиатра;
    - не подтверждают индивидуальную предрасположенность;
    - не являются доказательством соответствия законодательству о персональных данных.

Любое использование результатов анализа в клинических, научных или правовых целях
требует отдельной валидации уполномоченными специалистами.
