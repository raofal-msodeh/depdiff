# DepDiff — Discovery Notes

## المشكلة
ملفات `.env` هي الواقع العملي لإدارة التكوين المحلي للمطورين، لكنها بلا بنية: لا أنواع، لا قيم افتراضية موثقة، لا شروط بين البيئات، لا تحقق قبل التشغيل. المطور يكتشف أن `DB_PORT` نصي أو أن `API_KEY` مفقودة فقط عند فشل التطبيق في وقت التشغيل. Doppler [1] يوثق أن مقاطعة التدفق بسبب مشكلات .env تكلفة حقيقية. Infisical [2] تدعو لإهمال .env بسبب غياب الممارسة الموحدة.

## الألم المتكرر
- Stack Overflow: "How to manage environment variables in local development" — غياب إجماع حتى للمجموعات الصغيرة [3].
-dotenv-gad [4]: مكتبة تحقق schema حديثة (2026) لـ Node/Bun تدل على أن السوق ما زال يطلب التحقق الأنواعي.
- Zod env validation [5]: ممارسة شائعة لكنها تتطلب مكتبة ضخمة لكل مشروع Node.

## المقارنة
- python-dotenv: قراءة فقط، بلا schema.
- Doppler/Infisical: سحابية وتحتاج حسابًا.
- pydantic-settings: قوية لكنها عبء اعتمادية ثقيل لمشروع只想 تحقق .env بسيط.

## الأطروحة
للمطورين الذين يعانون من أخطاء تشغيل بسبب متغيرات .env مجهولة النوع أو مفقودة، يوفر DepDiff قالب TOML للتحقق من الأنواع والقيم الافتراضية الآمنة والشروط المشروطة بين البيئات، دون اعتماديات خارجية ودون خادم، عكس python-dotenv (بلا تحقق) وDoppler (سحابي) عبر كونه أداة محلية قابلة للتدقيق تنتج .env نهائيًا وmanifest تحقق.

[1]: https://www.doppler.com/blog/the-triumph-and-tragedy-of-env-files
[2]: https://medium.com/@tony.infisical/its-time-to-deprecate-the-env-file-for-a-better-stack-a519ac89bab0
[3]: https://softwareengineering.stackexchange.com/questions/352653/how-to-manage-environment-variables-in-local-development
[4]: https://github.com/kasimlyee/dotenv-gad
[5]: https://www.creatures.sh/blog/env-type-safety-and-validation/
