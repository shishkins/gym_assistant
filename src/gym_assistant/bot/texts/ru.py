"""Russian UI strings."""

from __future__ import annotations

from gym_assistant.domain.models import Equipment, ExerciseType, ExperienceLevel, Goal, Sex

# --- Access control -------------------------------------------------------

ACCESS_DENIED = (
    "🔒 Доступ к боту пока закрыт.\n\n"
    "Ваш Telegram ID: <code>{user_id}</code>\n"
    "Передайте его администратору, чтобы он добавил вас в список."
)

ACCESS_DENIED_SHORT = "Доступ закрыт. Ваш ID: {user_id}"

# --- Common ---------------------------------------------------------------

START_GREETING = (
    "👋 Привет, {name}!\n\n"
    "Я помогу вести дневник тренировок и следить за прогрессом.\n\n"
    "Что уже работает: /help"
)

START_RETURNING = "👋 С возвращением, {name}!\n\n{summary}"

HELP = (
    "<b>Что я умею</b>\n\n"
    "<b>Тренировки</b>\n"
    "/workout — начать или продолжить тренировку\n"
    "/last — последняя завершённая тренировка\n"
    "/exercises — справочник упражнений\n\n"
    "<b>Прогресс</b>\n"
    "/stats — отчёты и графики\n"
    "/export — выгрузить всё в CSV\n"
    "/ask — спросить ассистента о своих тренировках\n\n"
    "<b>Профиль и тело</b>\n"
    "/profile — профиль, просмотр и правка\n"
    "/weight — записать вес\n"
    "/photos — фото прогресса\n\n"
    "<b>Прочее</b>\n"
    "/menu — всё меню в одном месте\n"
    "/whoami — ваш уровень доступа\n"
    "/cancel — отменить текущее действие\n\n"
    "Во время тренировки подход можно просто написать: "
    "<code>80х8</code>, <code>80 8</code>, <code>100х5х3</code>.\n"
    "Можно прислать фото — сохраню как фото прогресса; "
    "если в подписи будет число, запишу его как вес.\n\n"
    "<i>В разработке:</i> голосовой ввод."
)

PING_OK = "🏓 На связи.\n\nВерсия: <code>{version}</code>\nОкружение: <code>{environment}</code>"

UNEXPECTED_ERROR = (
    "😔 Что-то пошло не так. Я записал ошибку и разберусь.\nПопробуйте ещё раз через минуту."
)

NOT_IMPLEMENTED_YET = "🚧 Этого я ещё не умею — функция в разработке.\nПока доступно: /help"

NOTHING_TO_CANCEL = "Нечего отменять."
CANCELLED = "Отменил. Что дальше — подскажет /help"

# --- Buttons --------------------------------------------------------------

BTN_SKIP = "Пропустить"
BTN_CANCEL = "Отмена"
BTN_DONE = "Готово"

SEX_LABELS = {Sex.MALE: "Мужской", Sex.FEMALE: "Женский"}

GOAL_LABELS = {
    Goal.MASS: "Набор массы",
    Goal.STRENGTH: "Сила",
    Goal.CUT: "Похудение",
    Goal.HEALTH: "Здоровье и форма",
}

EXPERIENCE_LABELS = {
    ExperienceLevel.BEGINNER: "Новичок",
    ExperienceLevel.INTERMEDIATE: "Средний",
    ExperienceLevel.ADVANCED: "Опытный",
}

BMI_LABELS = {
    "underweight": "недостаточный вес",
    "normal": "норма",
    "overweight": "избыточный вес",
    "obese": "ожирение",
}

# --- Onboarding -----------------------------------------------------------

ONBOARDING_INTRO = (
    "Давайте познакомимся — это займёт минуту.\n\n"
    "Данные нужны, чтобы советы были не общими, а под вас. "
    "Любой вопрос можно пропустить и заполнить позже через /profile."
)

ONBOARDING_SEX = "Ваш пол?"
ONBOARDING_BIRTH_DATE = (
    "Дата рождения?\n\n"
    "Формат: <code>31.12.1990</code>\n\n"
    "<i>Храню именно дату, а не возраст — так он не устареет через год.</i>"
)
ONBOARDING_HEIGHT = "Рост в сантиметрах?\n\nНапример: <code>178</code>"
ONBOARDING_GOAL = "Какая цель сейчас в приоритете?"
ONBOARDING_WEIGHT = (
    "Текущий вес в килограммах?\n\nНапример: <code>82.5</code>\n\n"
    "<i>Вес я храню историей, так что дальше можно взвешиваться командой /weight.</i>"
)

ONBOARDING_DONE = "✅ Готово, спасибо!\n\n{summary}\n\nПравить в любой момент: /profile"

ONBOARDING_BUSY = (
    "Сейчас идёт заполнение анкеты.\n\n"
    "Ответьте на вопрос, нажмите «Пропустить» — или /cancel, чтобы выйти."
)

ONBOARDING_DONE_EMPTY = "Хорошо, обойдёмся без анкеты.\n\nКогда захотите заполнить — /profile"

# --- Validation errors ----------------------------------------------------

ERROR_DATE_FORMAT = (
    "Не разобрал дату. Нужен формат <code>31.12.1990</code>.\n"
    "Попробуйте ещё раз или нажмите «Пропустить»."
)
ERROR_DATE_RANGE = (
    "Такая дата не подходит: возраст должен быть от 10 до 100 лет.\nПроверьте, пожалуйста."
)
ERROR_HEIGHT_FORMAT = "Нужно число, например <code>178</code>."
ERROR_HEIGHT_RANGE = "Рост должен быть от 100 до 250 см."
ERROR_WEIGHT_FORMAT = "Нужно число, например <code>82.5</code>."
ERROR_WEIGHT_RANGE = "Вес должен быть от 20 до 400 кг."

# --- Profile --------------------------------------------------------------

PROFILE_EMPTY = (
    "👤 <b>Профиль</b>\n\nПока пусто. Заполните — и советы станут точнее.\n\n"
    "Нажмите на любой пункт, чтобы указать значение."
)

PROFILE_HEADER = "👤 <b>Профиль</b>\n"
PROFILE_NOT_SET = "не указано"

PROFILE_FIELD_PROMPTS = {
    "sex": ONBOARDING_SEX,
    "birth_date": ONBOARDING_BIRTH_DATE,
    "height_cm": ONBOARDING_HEIGHT,
    "goal": ONBOARDING_GOAL,
    "experience_level": "Какой у вас опыт тренировок?",
}

PROFILE_UPDATED = "✅ Сохранил."

# --- Weight and measurements ---------------------------------------------

WEIGHT_PROMPT = "Текущий вес в килограммах?\n\nНапример: <code>82.5</code>"
WEIGHT_PROMPT_WITH_LAST = (
    "Текущий вес в килограммах?\n\nВ прошлый раз было <b>{last}</b> кг ({when})."
)

WEIGHT_SAVED = "✅ Записал: <b>{weight}</b> кг"
WEIGHT_SAVED_WITH_DELTA = "✅ Записал: <b>{weight}</b> кг\n\n{delta} за последний месяц"

WEIGHT_DELTA_UP = "📈 +{value} кг"
WEIGHT_DELTA_DOWN = "📉 −{value} кг"
WEIGHT_DELTA_SAME = "➡️ без изменений"

PHOTO_SAVED = "📸 Сохранил фото прогресса."
PHOTO_SAVED_WITH_WEIGHT = "📸 Сохранил фото и вес <b>{weight}</b> кг."

PHOTOS_EMPTY = (
    "Фотографий прогресса пока нет.\n\n"
    "Просто пришлите мне фото — я сохраню его с датой. "
    "Через пару месяцев такие снимки говорят больше, чем весы."
)
PHOTOS_HEADER = "📸 Фото прогресса: последние {shown} из {total}"
PHOTO_CAPTION = "{date}"
PHOTO_CAPTION_WITH_WEIGHT = "{date} · {weight} кг"

# --- Exercise catalogue ---------------------------------------------------

EQUIPMENT_LABELS = {
    Equipment.BARBELL: "штанга",
    Equipment.DUMBBELL: "гантели",
    Equipment.MACHINE: "тренажёр",
    Equipment.CABLE: "блок",
    Equipment.BODYWEIGHT: "свой вес",
    Equipment.KETTLEBELL: "гиря",
    Equipment.OTHER: "другое",
}

EXERCISE_TYPE_LABELS = {
    ExerciseType.WEIGHT_REPS: "вес × повторы",
    ExerciseType.BODYWEIGHT_REPS: "повторы",
    ExerciseType.TIME: "время",
    ExerciseType.DISTANCE: "дистанция",
}

EXERCISES_MENU = (
    "🏋️ <b>Справочник упражнений</b>\n\n"
    "Доступно упражнений: <b>{total}</b>\n"
    "Из них ваших: {own} · в избранном: {favourites}\n\n"
    "Найдите упражнение поиском или выберите группу мышц."
)

EXERCISES_SEARCH_PROMPT = (
    "Что ищем?\n\n"
    "Можно писать сокращённо и с опечатками: <code>бенч</code>, "
    "<code>приседанья</code>, <code>тяга</code>."
)

EXERCISES_SEARCH_EMPTY = (
    "Ничего не нашёл по запросу «{query}».\n\n"
    "Попробуйте короче или выберите группу мышц. "
    "Если такого упражнения у меня нет — добавьте своё."
)

EXERCISES_SEARCH_RESULTS = "Нашёл по запросу «{query}»:"
EXERCISES_GROUPS = "Выберите группу мышц:"
EXERCISES_GROUP_EMPTY = "В этой группе пока нет упражнений."
EXERCISES_GROUP_RESULTS = "<b>{group}</b>\n\nСначала базовые, потом изолирующие."

EXERCISES_FAVOURITES_EMPTY = (
    "В избранном пусто.\n\nОткройте любое упражнение и нажмите «В избранное» — они соберутся здесь."
)
EXERCISES_FAVOURITES = "⭐ <b>Избранное</b>"

EXERCISES_OWN_EMPTY = (
    "Своих упражнений пока нет.\n\n"
    "Добавьте то, чего нет в справочнике — оно будет видно только вам."
)
EXERCISES_OWN = "🛠 <b>Мои упражнения</b>"

# --- Exercise card --------------------------------------------------------

EXERCISE_CARD = "<b>{name}</b>\n{meta}"
EXERCISE_META = "{muscles} · {equipment} · {type}"
EXERCISE_COMPOUND = "базовое"
EXERCISE_ISOLATION = "изолирующее"
EXERCISE_OWN_BADGE = "\n\n<i>Ваше упражнение</i>"

EXERCISE_TIPS = "\n\n<b>Как делать</b>\n{tips}"
EXERCISE_MISTAKES = "\n\n<b>Частые ошибки</b>\n{mistakes}"

BTN_VIDEO = "▶️ Техника на видео"
BTN_VIDEO_SEARCH = "🔎 Найти видео"
BTN_FAV_ADD = "☆ В избранное"
BTN_FAV_REMOVE = "★ Убрать из избранного"
BTN_HIDE = "🚫 Скрыть из справочника"
BTN_BACK = "‹ Назад"

EXERCISE_FAV_ADDED = "Добавлено в избранное"
EXERCISE_FAV_REMOVED = "Убрано из избранного"
EXERCISE_HIDDEN = "Скрыл «{name}» — в поиске и списках его больше не будет."
EXERCISE_RESTORED = "Вернул «{name}» в справочник."
BTN_UNHIDE = "↩️ Вернуть"

# --- Creating an exercise -------------------------------------------------

EXERCISE_NEW_NAME = (
    "Как называется упражнение?\n\n"
    "Например: <code>Тяга Т-грифа</code>\n\n"
    "<i>Оно будет видно только вам.</i>"
)
EXERCISE_NEW_GROUP = "Какая группа мышц основная?"
EXERCISE_NEW_EQUIPMENT = "На чём выполняется?"
EXERCISE_NEW_TYPE = (
    "Что записываем в подходе?\n\n"
    "<i>От этого зависит, какие поля бот будет спрашивать во время тренировки.</i>"
)
EXERCISE_NEW_DONE = "✅ Добавил «{name}» в ваш справочник."
EXERCISE_NEW_DUPLICATE = (
    "Упражнение с таким названием у вас уже есть.\n\n"
    "Придумайте другое название или откройте существующее."
)
EXERCISE_NAME_TOO_SHORT = "Слишком коротко — нужно хотя бы три символа."
EXERCISE_NAME_TOO_LONG = "Слишком длинно. Уложитесь в 80 символов."

BTN_SEARCH = "🔎 Поиск"
BTN_GROUPS = "📂 По группам мышц"
BTN_FAVOURITES = "⭐ Избранное"
BTN_OWN = "🛠 Мои упражнения"
BTN_NEW = "➕ Добавить своё"

# --- Pagination and search mode -------------------------------------------

BTN_PREV_PAGE = "‹"
BTN_NEXT_PAGE = "›"
PAGE_INDICATOR = "{page}/{total}"

BTN_EXIT_SEARCH = "✖️ Выйти из поиска"
BTN_CANCEL_ACTION = "✖️ Отмена"
ACTION_CANCELLED = "Отменил."
LIST_COUNTER = "Показано {shown} из {total}"
BTN_TO_CATALOGUE = "📖 В справочник"

SEARCH_MODE_ON = (
    "🔎 <b>Режим поиска</b>\n\n"
    "Пишите названия — я буду искать по каждому сообщению.\n"
    "Сокращения и опечатки понимаю: <code>бенч</code>, <code>приседанья</code>.\n\n"
    "Выйти: кнопка ниже или /cancel"
)

SEARCH_MODE_AGAIN = "Ищите дальше или выйдите из режима."
SEARCH_MODE_OFF = "Вышел из поиска."

# --- Main menu ------------------------------------------------------------

MAIN_MENU = "<b>Что делаем?</b>"

BTN_MENU_WORKOUT = "🏋️ Тренировка"
BTN_MENU_EXERCISES = "📖 Упражнения"
BTN_MENU_PROFILE = "👤 Профиль"
BTN_MENU_WEIGHT = "⚖️ Записать вес"
BTN_MENU_PHOTOS = "📸 Фото прогресса"
BTN_MENU_HELP = "❔ Что я умею"

# --- Workouts -------------------------------------------------------------

WORKOUT_STARTED = "🏋️ <b>Тренировка началась</b>\n\nВыберите упражнение или просто напишите подход."

WORKOUT_PANEL = (
    "🏋️ <b>Тренировка идёт</b> · {duration}\n"
    "Подходов: <b>{sets}</b> · тоннаж: <b>{tonnage}</b> кг\n\n"
    "{exercises}"
)
WORKOUT_PANEL_EMPTY = "Пока ничего не записано."
WORKOUT_PANEL_LINE = "• {name} — {sets}"

WORKOUT_ALREADY_OPEN = "Тренировка уже идёт."
WORKOUT_NONE_OPEN = "Сейчас тренировки нет.\n\nНачать: /workout — или кнопкой ниже."

WORKOUT_PICK_EXERCISE = "Какое упражнение?"
WORKOUT_FREQUENT = "Ваши частые упражнения:"
WORKOUT_NO_FREQUENT = (
    "История пока пустая, поэтому частых упражнений нет.\n\nНайдите нужное поиском."
)

# --- Exercise panel inside a workout --------------------------------------

WORKOUT_EXERCISE_FIRST_TIME = "<b>{name}</b>\n\n<i>Раньше не делали — записываю с нуля.</i>"
WORKOUT_EXERCISE_HISTORY = "<b>{name}</b>\n\nВ прошлый раз ({when}):\n{sets}"
WORKOUT_EXERCISE_BEST = "\nЛучший результат: <b>{best}</b> кг (расчётный максимум)"
WORKOUT_EXERCISE_TODAY = "\n\n<b>Сегодня:</b>\n{sets}"

WORKOUT_SET_LINE = "  {index}. {value}"
WORKOUT_SET_LINE_WARMUP = "  {index}. {value} · разминка"

WORKOUT_ENTRY = "\n\nЗаписать: <b>{weight}</b> кг × <b>{reps}</b>"
WORKOUT_ENTRY_BODYWEIGHT = "\n\nЗаписать: <b>{reps}</b> повторов"

WORKOUT_SET_SAVED = "✅ {value}"
WORKOUT_SETS_SAVED = "✅ {count} подхода: {value}"
# The record is the weight on the bar, so the message shows the set.
WORKOUT_RECORD = "🏆 <b>Личный рекорд!</b> {value}"
WORKOUT_RECORD_BEATEN = "🏆 <b>Личный рекорд!</b> {value}\nПрежний максимум: {previous} кг"
WORKOUT_RECORD_ESTIMATE = "\n<i>Расчётный максимум: ~{estimate} кг</i>"

WORKOUT_SET_UNDONE = "↩️ Убрал: {value}"
WORKOUT_NOTHING_TO_UNDO = "Отменять нечего — подходов ещё нет."

WORKOUT_NEED_EXERCISE = (
    "Не понял, к какому упражнению это относится.\n\n"
    "Напишите с названием — <code>жим 80х8</code> — или выберите упражнение кнопкой."
)
WORKOUT_EXERCISE_NOT_FOUND = (
    "Не нашёл упражнение «{query}».\n\nПопробуйте иначе или выберите из списка."
)
WORKOUT_SET_FORMAT_ERROR = (
    "Не разобрал подход.\n\n"
    "Примеры: <code>80х8</code>, <code>82,5х8</code>, <code>80х8х3</code>, "
    "<code>12</code>, <code>60с</code>, <code>жим 80х8</code>"
)
WORKOUT_SET_RANGE_ERROR = "Значения вне разумных пределов — проверьте, пожалуйста."

# --- Finishing ------------------------------------------------------------

WORKOUT_FINISHED = (
    "🏁 <b>Тренировка завершена</b>\n\n"
    "Длительность: <b>{duration}</b>\n"
    "Подходов: <b>{sets}</b> (рабочих {working})\n"
    "Тоннаж: <b>{tonnage}</b> кг\n\n"
    "{exercises}"
)
WORKOUT_FINISHED_EMPTY = "Тренировка закрыта без записей — в историю не пойдёт."
WORKOUT_FINISHED_RECORDS = "\n\n🏆 <b>Рекорды:</b>\n{records}"
WORKOUT_RECORD_LINE = "  • {name} — {best} кг"

WORKOUT_LAST_NONE = "Завершённых тренировок пока нет."
WORKOUT_LAST_HEADER = "🏁 <b>Последняя тренировка</b> · {when}\n\n"

WORKOUT_STALE_CLOSED = (
    "Закрыл тренировку, которая осталась открытой с {when} — видимо, забыли нажать «Завершить»."
)

# --- Workout buttons ------------------------------------------------------

BTN_WORKOUT_START = "🏋️ Начать тренировку"
BTN_WORKOUT_CONTINUE = "🏋️ Продолжить тренировку"
BTN_WORKOUT_FINISH = "🏁 Завершить"
BTN_WORKOUT_ADD_SET = "✅ Записать"
BTN_WORKOUT_REPEAT = "🔁 Повторить подход"
BTN_WORKOUT_UNDO = "↩️ Отменить последний"
BTN_WORKOUT_OTHER = "🔀 Другое упражнение"
BTN_WORKOUT_FIND = "🔎 Найти упражнение"
BTN_WORKOUT_PANEL = "🏋️ К тренировке"
BTN_WARMUP = "🔥 Разминочный"

# --- Input help -----------------------------------------------------------

WORKOUT_INPUT_HELP = (
    "<b>Как записывать подходы</b>\n\n"
    "Во время тренировки просто пишите — кнопки не нужны:\n\n"
    "<code>80х8</code> — вес × повторы\n"
    "<code>82,5х8</code> — запятая тоже работает\n"
    "<code>80 8</code> · <code>80x8</code> · <code>80*8</code> · <code>80 на 8</code>"
    " — то же самое\n"
    "<code>80х8х3</code> — три одинаковых подхода\n"
    "<code>жим 80х8</code> — сразу с упражнением\n"
    "<code>присед</code> — просто переключиться на другое\n\n"
    "<b>Дополнения</b>\n"
    "<code>80х8 разминка</code> — разминочный (или <code>р 80х8</code>)\n"
    "<code>80х8 @8</code> — с оценкой усилия RPE\n\n"
    "<b>Не только железо</b>\n"
    "<code>12</code> — повторы со своим весом\n"
    "<code>60с</code> · <code>1:30</code> — время\n"
    "<code>100м</code> — дистанция"
)

BTN_WORKOUT_HELP = "❔ Как записывать"
BTN_WORKOUT_CATALOGUE = "📖 Справочник"
BTN_LOG_THIS = "➕ Записать подход"

# --- Statistics -----------------------------------------------------------

STATS_MENU = (
    "📊 <b>Статистика</b>\n\n"
    "Период: <b>{period}</b>\n"
    "Тренировок за период: <b>{workouts}</b> · подходов: <b>{sets}</b>\n\n"
    "Выберите отчёт."
)

STATS_PERIOD_LABELS = {
    "1m": "месяц",
    "3m": "3 месяца",
    "6m": "полгода",
    "1y": "год",
    "all": "всё время",
}

STATS_PICK_EXERCISE = "По какому упражнению построить динамику?"
STATS_NO_EXERCISES = (
    "Пока нечего показывать: за этот период нет ни одного записанного подхода.\n\n"
    "Начните тренировку — /workout"
)

STATS_NOT_ENOUGH = (
    "За период «{period}» рисовать нечего — нет ни одной записи.\n\n"
    "Попробуйте период побольше или запишите тренировку."
)

# Shown under a chart built from a single day or week: the picture is honest,
# but it is a dot, and saying so is cheaper than letting it look like a trend.
STATS_THIN = "Пока одна точка. Со следующей тренировкой появится линия, с третьей — тренд."

STATS_EMPTY = "За период «{period}» записей нет."

STATS_RECORDS_HEADER = "🏆 <b>Личные рекорды</b>{page}\n\n"
STATS_RECORDS_LINE = "<b>{name}</b>\n  {weight} кг × {reps} · {when}"
STATS_RECORDS_ESTIMATE = "\n  <i>расчётный максимум {estimate} кг</i>"
STATS_RECORDS_EMPTY = "Рекордов пока нет — они появятся, как только запишете подход с весом."

STATS_LAST_WITH_NONE = "Завершённых тренировок с этим упражнением пока нет."

STATS_SUMMARY = (
    "📊 <b>Итоги за {period}</b>\n\n"
    "Тренировок: <b>{workouts}</b>\n"
    "Подходов: <b>{sets}</b> (рабочих {working})\n"
    "Тоннаж: <b>{tonnage}</b> кг\n"
    "В среднем за тренировку: <b>{per_workout}</b> кг"
)

# --- Export ---------------------------------------------------------------

EXPORT_READY = (
    "⬇️ Ваши данные: <b>{sets}</b> подходов, <b>{measurements}</b> замеров.\n\n"
    "<i>CSV с разделителем «;» и BOM — Excel откроет без плясок с кодировкой.</i>"
)
EXPORT_EMPTY = "Выгружать пока нечего — нет ни подходов, ни замеров."

# --- Profile records ------------------------------------------------------

PROFILE_RECORDS = "\n\n🏆 <b>Максимумы</b>\n{records}"
PROFILE_RECORD_LINE = "  {name} — <b>{weight}</b> кг × {reps}"
BTN_PROFILE_RECORDS = "🏆 Все рекорды"

# --- Statistics buttons ---------------------------------------------------

BTN_STATS_PROGRESS = "📈 Динамика упражнения"
BTN_STATS_TONNAGE = "🏋️ Тоннаж по неделям"
BTN_STATS_VOLUME = "🎯 Объём по группам"
BTN_STATS_WEIGHT = "⚖️ Вес тела"
BTN_STATS_RECORDS = "🏆 Личные рекорды"
BTN_STATS_FREQUENCY = "📅 Частота тренировок"
BTN_STATS_SUMMARY = "🧮 Итоги"
BTN_STATS_EXPORT = "⬇️ Выгрузить CSV"
BTN_STATS_PERIOD = "🗓 Период: {period}"
BTN_STATS_LAST_WITH = "📋 Последняя тренировка с ним"
BTN_STATS_PICK_OTHER = "📈 Другое упражнение"
BTN_MENU_STATS = "📊 Статистика"


# --- Roles and admin ------------------------------------------------------

WHOAMI = (
    "Ваш Telegram ID: <code>{telegram_id}</code>\nУровень доступа: <b>{role}</b>\nСрок: {until}"
)

ADMIN_FOREVER = "бессрочно"
ADMIN_UNTIL = "на {days} дн."
ADMIN_UNTIL_DATE = "до {when}"
ADMIN_LAPSED = "истёк {when} — доступ уже обычный"

ADMIN_GRANT_USAGE = (
    "<b>/grant</b> — выдать доступ.\n\n"
    "<code>/grant &lt;telegram_id&gt; &lt;роль&gt; [дней]</code>\n\n"
    "Роли: <code>admin</code>, <code>sub</code> (подписчик), <code>user</code> (обычный).\n"
    "Без числа дней — бессрочно.\n\n"
    "Например: <code>/grant 402666721 sub 30</code>"
)
ADMIN_REVOKE_USAGE = (
    "<b>/revoke</b> — вернуть обычный доступ.\n\n<code>/revoke &lt;telegram_id&gt;</code>"
)
ADMIN_BAD_ID = "«{value}» не похоже на Telegram ID — нужно число."
ADMIN_BAD_ROLE = (
    "Роли «{value}» нет. Доступны: <code>admin</code>, <code>sub</code>, <code>user</code>."
)
ADMIN_BAD_DAYS = "«{value}» не похоже на число дней — нужно целое положительное."
ADMIN_USER_UNKNOWN = (
    "Пользователя <code>{telegram_id}</code> в базе нет.\n\n"
    "Он появится, как только напишет боту /start — попросите его это сделать."
)
ADMIN_GRANTED = "{who} → <b>{role}</b>, {until}."
ADMIN_REVOKED = "{who} снова обычный пользователь."
ADMIN_NOTHING_TO_REVOKE = "У него и так обычный доступ."
ADMIN_USERS_HEADER = "👥 <b>Выданные доступы</b>\n\n"
ADMIN_USER_LINE = "{who} · <code>{telegram_id}</code>\n  {role}, {until}"
ADMIN_USERS_EMPTY = (
    "Никому ничего не выдано — все пользователи обычные.\n\n"
    "Выдать: <code>/grant &lt;telegram_id&gt; sub 30</code>"
)

ACCESS_NEEDS_SUBSCRIPTION = (
    "Эта возможность доступна по подписке.\n\n"
    "Ваш ID: <code>{telegram_id}</code> — передайте его администратору."
)


# --- AI assistant ---------------------------------------------------------

AI_USAGE = (
    "<b>/ask</b> — спросить ассистента о твоих тренировках.\n\n"
    "Он видит твою историю и отвечает цифрами из неё.\n\n"
    "Например:\n"
    "<code>/ask как растёт жим за 3 месяца</code>\n"
    "<code>/ask что у меня недорабатывается</code>\n"
    "<code>/ask я застрял в приседе?</code>\n\n"
    "<code>/ai_reset</code> — начать разговор заново\n"
    "<code>/ai_usage</code> — сколько потрачено за месяц"
)

AI_NOT_CONFIGURED = (
    "Ассистент не настроен: у бота нет ключа к API.\nЭто чинится на сервере, а не здесь."
)
AI_UNAVAILABLE = (
    "Не смог достучаться до ассистента. Попробуй через минуту — если повторится, я разберусь."
)
AI_BUDGET_SPENT = (
    "Месячный бюджет на ассистента исчерпан.\n\n"
    "Он обновится первого числа. Статистика и дневник работают как обычно."
)
AI_EMPTY_ANSWER = "Ассистент промолчал. Попробуй переформулировать вопрос."
AI_RESET = "Разговор начат заново — прошлый контекст забыт."
AI_RESET_EMPTY = "Активного разговора и не было."

AI_USAGE_REPORT = (
    "💸 <b>Расходы на ассистента в этом месяце</b>\n\n"
    "Ты: <b>${mine}</b>\n"
    "Все вместе: <b>${everyone}</b> из ${limit}"
)
