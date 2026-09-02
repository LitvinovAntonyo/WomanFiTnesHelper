# Визуальный стандарт карточек упражнений

Этот файл фиксирует визуальный канон для всех новых упражнений. Существующие изображения
из `app/assets/exercises/` используются как **референсы персонажа и стиля**, а не как
объекты для перезаписи.

## Неизменяемые признаки

- одна и та же взрослая девушка: узнаваемое лицо и пропорции из текущих карточек;
- каштановые волосы, низкий хвост, несколько свободных прядей у лица;
- облегающий бирюзовый спортивный топ;
- тёмно-серые легинсы с высокой посадкой;
- белые спортивные кроссовки;
- маленькая контурная татуировка-сердце возле левой ключицы;
- современный нейтрально-серый зал, тёмное резиновое покрытие, сдержанные фиолетовые
  акценты;
- фотореалистичная фитнес-съёмка, естественная кожа и ткань;
- квадрат 1:1, два равных кадра с тонким разделителем;
- без текста, стрелок, логотипов, водяных знаков и посторонних людей.

## Шаблон промпта

```text
Use case: photorealistic-natural
Asset type: square Telegram exercise technique card
Primary request: generate a new <EXERCISE> technique card; do not edit the references.
Input images: current exercise cards are identity, outfit, gym, lighting, and visual-style references only.
Scene/backdrop: the same clean modern neutral-gray gym with dark rubber flooring and understated purple accents.
Subject: preserve the same woman's recognizable face, body proportions, brunette low ponytail, teal fitted sports crop top, charcoal high-waisted leggings, white training shoes, and small outline heart tattoo near the left collarbone.
Style/medium: polished photorealistic fitness photography matching the references, natural skin and fabric texture.
Composition/framing: 1:1 square card split into two equal panels; full body and relevant equipment visible. First panel shows the starting position, second panel shows the end position.
Constraints: exact same identity and outfit in both panels; anatomically and mechanically correct exercise technique; no text, arrows, logos, labels, watermark, extra people, cropped feet, or duplicated limbs.
```

К общему шаблону всегда добавляется отдельное точное описание техники конкретного
упражнения: положение суставов, траектория, хват, настройка тренажёра и запрещённые ошибки.
Карточка не добавляется в программу, пока изображение и текст техники не проверены вместе.

## Кардио, созданное для этой версии

- `cardio_treadmill.png` — лёгкий бег на дорожке, естественный шаг, без опоры на поручни;
- `cardio_elliptical.png` — взаимная работа рук и ног, стопы полностью на педалях;
- `cardio_bike.png` — правильная высота седла и небольшое сгибание колена в нижней точке.

Все три изображения созданы встроенным ImageGen по трём существующим карточкам-референсам
и сохранены в проекте в размере 1254×1254.

## Тренажёры, созданные для приоритетной программы

- `seated_leg_curl.png` — сгибание ног сидя для задней поверхности бедра;
- `glute_kickback.png` — поочерёдное отведение ноги назад в ягодичном тренажёре;
- `leg_extension.png` — разгибание ног сидя для квадрицепса;
- `hip_abduction.png` — разведение бёдер с неподвижным тазом;
- `hip_adduction.png` — сведение бёдер с контролируемым возвратом.
- `hack_squat.png` — гакк-присед на наклонной машине с опорой спины и таза.
- `pec_deck.png` — сведение рук в тренажёре с фиксированным мягким сгибом локтей.

Карточки созданы встроенным ImageGen по тому же шаблону и тем же трём визуальным
референсам. Во всех пяти сохранены героиня, одежда, зал, квадратная двухкадровая
композиция и размер 1254×1254; меняются только тренажёр и техника упражнения.
