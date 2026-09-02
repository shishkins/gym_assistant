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
    "<b>Что я умею сейчас</b>\n\n"
    "<b>Профиль и тело</b>\n"
    "/profile — профиль, просмотр и правка\n"
    "/weight — записать вес\n"
    "/photos — фото прогресса\n\n"
    "<b>Прочее</b>\n"
    "/start — начало работы\n"
    "/cancel — отменить текущее действие\n"
    "/ping — проверка связи\n\n"
    "Можно просто прислать фото — я сохраню его как фото прогресса.\n"
    "Если в подписи будет число, запишу его как вес.\n\n"
    "<i>В разработке:</i> тренировки, статистика, "
    "голосовой ввод и AI-ассистент."
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

BTN_MENU_EXERCISES = "🏋️ Упражнения"
BTN_MENU_PROFILE = "👤 Профиль"
BTN_MENU_WEIGHT = "⚖️ Записать вес"
BTN_MENU_PHOTOS = "📸 Фото прогресса"
BTN_MENU_HELP = "❔ Что я умею"
