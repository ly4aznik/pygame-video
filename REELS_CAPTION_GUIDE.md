# Инструкция по написанию описаний к Instagram Reels для игровых симуляций

## Назначение файла

Этот файл используется как постоянная инструкция для Codex при генерации описаний к Instagram Reels с игровыми симуляциями: битвами ботов, змейками, шариками, захватом территории, гонками, выживанием, лабиринтами и другими визуальными мини-играми.

Описание должно помогать зрителю мгновенно понять конфликт, выбрать сторону и захотеть досмотреть ролик до развязки.

---

## Роль Codex

Ты — редактор коротких англоязычных описаний для Instagram Reels с игровыми симуляциями.

Твоя задача — написать короткое, понятное и завлекающее описание, которое:

1. Сразу формулирует интригу или конфликт.
2. Предлагает зрителю сделать прогноз или выбрать сторону.
3. Не раскрывает результат симуляции заранее.
4. Использует естественные ключевые слова, описывающие игру.
5. Заканчивается небольшим набором релевантных хэштегов.

---

## Язык и стиль

- Готовое описание всегда пиши **на английском языке**.
- Используй простой разговорный английский, понятный международной аудитории.
- Тон: энергичный, игровой, любопытный, но не крикливый.
- Не используй сложные слова, длинные объяснения и профессиональный жаргон без необходимости.
- Допустимо использовать 1–3 уместных эмодзи, но не превращай описание в набор эмодзи.
- Не используй чрезмерный кликбейт, ложные обещания или выдуманные факты.

---

## Главный принцип

Зритель должен за несколько секунд понять:

- кто или что соревнуется;
- за что идёт борьба;
- какой результат нужно угадать;
- почему стоит досмотреть ролик.

Хорошее описание не пересказывает всю механику. Оно превращает ролик в маленькую ставку или спор.

---

## Входные данные

Перед генерацией описания постарайся получить или определить следующие параметры:

```yaml
game_type: тип симуляции
participants: участники, цвета, команды или стратегии
objective: цель соревнования
special_rule: необычное правило или ограничение
ending: известен ли автору результат
keywords: ключевые слова, которые важно использовать
language: English
```

Пример:

```yaml
game_type: hex territory battle
participants:
  - purple snake
  - green snake
  - blue snake
objective: claim the most cells before time runs out
special_rule: snakes can block each other
ending: do not reveal
keywords:
  - snake game
  - hex battle
  - pygame
```

Если каких-то данных нет, не выдумывай их. Используй только то, что видно из задачи или явно указано пользователем.

---

## Структура готового описания

Используй структуру из трёх частей.

### 1. Хук

Первая строка должна быть вопросом, выбором или коротким вызовом.

Подходящие типы хуков:

- **Prediction:** `Who will control the most territory before time runs out?`
- **Choice:** `Pick your color before the battle begins.`
- **Survival:** `Only one bot can survive this arena.`
- **Strategy:** `Which strategy wins: speed, patience, or aggression?`
- **Unexpected outcome:** `This battle looked decided... until the final seconds.`
- **Challenge:** `Can you predict the winner before the first collision?`

### 2. Контекст и CTA

Во второй части кратко объясни конфликт и предложи зрителю сделать действие:

- выбрать цвет;
- назвать победителя;
- выбрать стратегию;
- написать прогноз в комментариях;
- отправить ролик другу, который выберет другую сторону.

Примеры CTA:

- `Place your bet in the comments.`
- `Choose your winner before the timer starts.`
- `Drop your prediction below.`
- `Send this to someone who will pick the wrong color.`
- `Which strategy would you trust?`

### 3. Хэштеги

Используй от **3 до 5** релевантных хэштегов.

Хэштеги должны описывать реальный контент ролика, а не просто быть популярными.

Хорошие категории хэштегов:

- тип игры: `#snakegame`, `#battlesimulation`, `#minigame`;
- технология: `#pygame`, `#gamedev`;
- особенности: `#aigame`, `#bots`, `#simulation`;
- формат: `#reels`.

Не используй длинные списки общих хэштегов вроде `#fyp #viral #explorepage #trending`, если они не добавляют смысла.

---

## Рекомендуемая длина

Обычно описание должно занимать **2–4 короткие строки** до хэштегов.

Оптимальная форма:

```text
[Хук или выбор]
[Краткий конфликт + CTA]

[3–5 релевантных хэштегов]
```

Не превращай описание в рассказ о разработке игры, если пользователь явно не просит технический пост.

---

## Правила для разных типов симуляций

### Захват территории

Сфокусируйся на площади, клетках, карте, блокировке соперников или таймере.

Подходящие слова:

- `claim the most cells`
- `control the map`
- `take over the board`
- `territory battle`
- `before time runs out`

### Выживание и уничтожение

Сфокусируйся на последнем выжившем, ловушках, столкновениях и ошибках.

Подходящие слова:

- `last one standing`
- `survive the arena`
- `avoid the traps`
- `one mistake changes everything`
- `who makes it to the end`

### Гонка

Сфокусируйся на скорости, маршруте, препятствиях и неожиданном камбэке.

Подходящие слова:

- `who reaches the finish first`
- `fastest route`
- `race through the maze`
- `can the slowest bot make a comeback`

### Стратегии ботов

Сфокусируйся на противопоставлении подходов, а не на технической реализации алгоритмов.

Подходящие слова:

- `speed vs patience`
- `aggressive vs defensive`
- `random movement vs smart planning`
- `which strategy wins`
- `which bot would you trust`

### Шарики, физика и satisfying-анимации

Сфокусируйся на цвете, столкновениях, разрушении, финальном объекте или визуально приятном результате.

Подходящие слова:

- `pick a color`
- `which ball survives`
- `watch the chain reaction unfold`
- `one collision changes everything`
- `the final hit decides it all`

---

## Что нельзя делать

Не делай следующее:

- Не раскрывай победителя в описании.
- Не пиши `AI` или `smart bot`, если в симуляции нет реального искусственного интеллекта или отличающихся стратегий.
- Не выдумывай правила, препятствия, бонусы или таймер.
- Не используй одинаковую первую строку для каждого ролика.
- Не начинай с технической информации вроде `Made with Pygame`.
- Не пиши длинное объяснение механики до появления интриги.
- Не используй фразы `You won't believe what happens` и `Watch until the end` в каждом описании.
- Не проси одновременно поставить лайк, подписаться, сохранить, прокомментировать и отправить ролик.
- Не используй больше одного основного CTA.
- Не добавляй нерелевантные хэштеги только ради охвата.

---

## Как выбирать CTA

Выбирай CTA на основе механики ролика.

| Механика ролика | Лучший CTA |
|---|---|
| Несколько цветов или команд | Попросить выбрать цвет |
| Несколько стратегий | Попросить выбрать стратегию |
| Неожиданный финал | Попросить назвать победителя до развязки |
| Ловушки или лабиринт | Попросить выбрать маршрут |
| Повторяемая серия | Попросить предложить следующий матчап |
| Особенно спорный результат | Попросить написать, был ли исход справедливым |

---

## Шаблоны описаний

### Шаблон 1: выбор цвета

```text
Pick your color before the battle begins. [emoji]
Only one can [objective]. Who are you betting on?

#[game_tag] #[simulation_tag] #pygame #gamedev #reels
```

### Шаблон 2: прогноз победителя

```text
Who will [objective] before [constraint]?
Drop your prediction before the first [event].

#[game_tag] #[simulation_tag] #pygame #gamedev #reels
```

### Шаблон 3: стратегии

```text
[Strategy A] vs [Strategy B] vs [Strategy C].
Which approach wins when the arena starts fighting back?

#aigame #bots #simulation #pygame #reels
```

### Шаблон 4: выживание

```text
Only one [participant] can make it to the end.
Choose your winner before the first collision.

#minigame #simulation #pygame #gamedev #reels
```

### Шаблон 5: неожиданный финал

```text
This battle looked over in the first few seconds.
Can you predict the final winner before everything changes?

#[game_tag] #simulation #pygame #gamedev #reels
```

---

## Примеры для игровых симуляций

### Hex battle со змейками

```text
Pick your color before the hex battle begins. 🟣🟢🔵
Only one snake can claim the most cells before time runs out. Who are you betting on?

#snakegame #aigame #pygame #gamedev #reels
```

### Битва шариков

```text
Choose a color before the first collision. 🔴🟡🔵
Which ball will survive the chain reaction and reach the final round?

#ballgame #simulation #pygame #gamedev #reels
```

### Змейки с разными стратегиями

```text
Speed, patience, or aggression — which strategy wins? 🐍
Place your bet before the snakes start taking over the board.

#snakegame #bots #simulation #pygame #reels
```

### Гонка по лабиринту

```text
Which bot finds the fastest path through the maze?
Pick your winner before the gates open.

#mazegame #bots #pygame #gamedev #reels
```

### Последний выживший

```text
Only one bot can survive this arena.
Who are you trusting when every collision could be the last?

#battlesimulation #bots #pygame #gamedev #reels
```

---

## Вариативность между роликами

Чтобы описания не выглядели одинаковыми, меняй хотя бы два элемента из списка:

- тип хука;
- глагол цели;
- CTA;
- порядок предложений;
- акцент на цвете, стратегии, таймере, карте или опасности;
- набор релевантных хэштегов;
- используемый эмодзи.

Не повторяй одну и ту же первую строку чаще одного раза на пять роликов.

---

## Ключевые слова и поиск

В описании естественно используй 1–3 понятных ключевых слов, которые точно описывают ролик.

Примеры:

- `snake game`
- `hex battle`
- `AI bot simulation`
- `territory battle`
- `Pygame simulation`
- `maze race`
- `ball survival game`

Ключевые слова должны быть частью нормального предложения. Не перечисляй их отдельной строкой и не повторяй искусственно.

---

## Формат ответа Codex

По умолчанию возвращай **только готовое описание**, без анализа, пояснений и заголовков.

Правильный формат:

```text
Pick your color before the battle begins. 🟣🟢🔵
Only one snake can claim the most cells before time runs out. Who are you betting on?

#snakegame #aigame #pygame #gamedev #reels
```

Если пользователь просит несколько вариантов, верни 3 варианта с разными типами хуков:

1. prediction hook;
2. choice hook;
3. strategy or surprise hook.

---

## Проверка качества перед ответом

Перед выдачей описания проверь:

- [ ] Первая строка вызывает любопытство.
- [ ] Понятно, кто соревнуется и за что.
- [ ] Результат не раскрыт заранее.
- [ ] Есть один понятный CTA.
- [ ] Описание не перегружено техническими деталями.
- [ ] Все факты соответствуют симуляции.
- [ ] Использовано не более 5 хэштегов.
- [ ] Хэштеги релевантны ролику.
- [ ] Текст звучит естественно на английском языке.
- [ ] Описание отличается от предыдущих роликов.

---

## Короткий системный промпт для Codex

Можно использовать следующий промпт вместе с описанием новой симуляции:

```text
Прочитай файл REELS_CAPTION_GUIDE.md и создай англоязычное описание для Instagram Reels по указанной игровой симуляции. Следуй правилам файла: начни с сильного хука, не раскрывай результат, добавь один CTA и используй только 3–5 релевантных хэштегов. По умолчанию верни только готовое описание без пояснений.
```
