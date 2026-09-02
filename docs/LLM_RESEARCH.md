# Исследование LLM для фитнес-бота

Актуальность проверки: 2 сентября 2026 года. Сравнение основано на официальных тарифах,
лимитах и документации. Доступ из конкретного VPS всё равно нужно подтвердить сетевым
запросом после аудита сервера: часть провайдеров не публикует исчерпывающий список стран.

| Провайдер | Модель | Стоимость и бесплатный лимит | Карта | Русский / скорость | Ограничения | Вывод |
|---|---|---|---|---|---|---|
| GroqCloud | `openai/gpt-oss-20b` | Free: 30 RPM, 1000 RPD, 8000 TPM, 200 000 TPD | Не нужна для Free | Хороший русский; около 1000 токенов/с по каталогу | Нужен API key; нет SLA; фактическую доступность из VPS надо проверить | **Основной выбор** |
| OpenRouter | `openrouter/free` или конкретная `:free` | 50 запросов/день; 1000/день после покупки не менее $10 credits | Для чистого Free не нужна | Качество и скорость меняются вместе с выбранной моделью | Free router может выбрать случайную модель; низкая стабильность | Резервный адаптер, не основной production-вариант |
| Hugging Face Inference Providers | Модель из доступных providers | Free user получает только $0.10 credits в месяц | Для стартового кредита не нужна; для PAYG нужны credits | Зависит от модели и backend | Лимит слишком мал даже для спокойного личного бота | Только эксперименты |
| Cloudflare Workers AI | например `@cf/meta/llama-3.1-8b-instruct-fp8-fast` | 10 000 neurons/день; text generation до 300 RPM | Для Workers Free обычно не нужна | Русский средний; скорость хорошая | Собственная единица тарификации; часть новых моделей требует Paid | Рабочий резерв, но сложнее Groq |
| Google Gemini API | доступная Flash-модель | У ряда моделей бесплатные input/output tokens; точная quota зависит от проекта/модели | Free не требует billing | Хороший русский; высокая скорость | Россия отсутствует в официальном списке доступных регионов; free-данные могут использоваться для улучшения сервисов | Не выбирать для этого размещения без подтверждённой допустимой географии |
| Локально, Ollama | `qwen3:4b-instruct` | Бесплатно; вес модели около 2.5 ГБ | Нет | Русский хороший для малого класса; CPU-скорость зависит от VPS | Нужны ориентировочно от 4–6 ГБ свободной RAM и запас CPU; модель нельзя скачивать до аудита | Выбирать только если VPS имеет безопасный запас ресурсов |

## Выбор

Для первой версии выбран GroqCloud + `openai/gpt-oss-20b`:

- модель находится в production-каталоге, а не в preview;
- бесплатного лимита 1000 запросов в день более чем достаточно для одного пользователя;
- OpenAI-совместимый API делает замену провайдера простой;
- ключ не обязателен для работоспособности бота: при его отсутствии, timeout, 429 или 5xx
  приложение немедленно использует локальные короткие шаблоны;
- по умолчанию в примере окружения стоит `LLM_PROVIDER=template`. Переключение на Groq
  делается только после фактической проверки API с VPS и локального внесения ключа.

Модель Qwen на Groq не выбрана основной, потому что актуальная Qwen 3.6/3.8 27B в каталоге
помечена preview и может быть снята с меньшим сроком предупреждения. `gpt-oss-20b` указан
как production model и как замена уже снятых старых Llama-моделей.

## Официальные источники

- [Groq free rate limits](https://console.groq.com/docs/rate-limits)
- [Groq supported/production models](https://console.groq.com/docs/models)
- [Groq model deprecations](https://console.groq.com/docs/deprecations)
- [Groq data retention](https://console.groq.com/docs/your-data)
- [Groq free tier without a card](https://community.groq.com/t/is-there-a-free-tier-and-what-are-its-limits/790)
- [OpenRouter pricing](https://openrouter.ai/pricing)
- [OpenRouter FAQ and free limits](https://openrouter.ai/docs/faq)
- [OpenRouter free model router](https://openrouter.ai/docs/cookbook/get-started/free-models-router-playground)
- [Hugging Face Inference Providers pricing](https://huggingface.co/docs/inference-providers/pricing)
- [Cloudflare Workers AI pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/)
- [Cloudflare Workers AI limits](https://developers.cloudflare.com/workers-ai/platform/limits/)
- [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing)
- [Gemini API available regions](https://ai.google.dev/gemini-api/docs/available-regions)
- [Ollama Qwen3 model sizes](https://ollama.com/library/qwen3/tags)
