# Third-Party Licenses

This file lists all third-party open-source components used in **Journiv**.
Each dependency retains its original license; no ownership is claimed over third-party code.

Journiv’s original source code is licensed separately under the
[**PolyForm Noncommercial License 1.0.0**](./LICENSE.md).

---

## Python Dependencies

| Package                   | License         | Source                                                                                                   |
| ------------------------- | --------------- | -------------------------------------------------------------------------------------------------------- |
| fastapi                   | MIT             | [https://github.com/tiangolo/fastapi](https://github.com/tiangolo/fastapi)                               |
| uvicorn                   | BSD-3-Clause    | [https://github.com/encode/uvicorn](https://github.com/encode/uvicorn)                                   |
| pydantic                  | MIT             | [https://github.com/pydantic/pydantic](https://github.com/pydantic/pydantic)                             |
| sqlmodel                  | MIT             | [https://github.com/tiangolo/sqlmodel](https://github.com/tiangolo/sqlmodel)                             |
| sqlalchemy                | MIT             | [https://github.com/sqlalchemy/sqlalchemy](https://github.com/sqlalchemy/sqlalchemy)                     |
| alembic                   | MIT             | [https://github.com/sqlalchemy/alembic](https://github.com/sqlalchemy/alembic)                           |
| psycopg2-binary           | LGPL-3.0        | [https://github.com/psycopg/psycopg2](https://github.com/psycopg/psycopg2)                               |
| python-jose[cryptography] | MIT             | [https://github.com/mpdavis/python-jose](https://github.com/mpdavis/python-jose)                         |
| passlib[argon2]           | BSD-2-Clause    | [https://github.com/serge-sans-paille/passlib](https://github.com/serge-sans-paille/passlib)             |
| argon2-cffi               | MIT             | [https://github.com/hynek/argon2_cffi](https://github.com/hynek/argon2_cffi)                             |
| python-multipart          | Apache-2.0      | [https://github.com/Kludex/python-multipart](https://github.com/Kludex/python-multipart)                 |
| pydantic-settings         | MIT             | [https://github.com/pydantic/pydantic-settings](https://github.com/pydantic/pydantic-settings)           |
| python-dotenv             | BSD-3-Clause    | [https://github.com/theskumar/python-dotenv](https://github.com/theskumar/python-dotenv)                 |
| slowapi                   | MIT             | [https://github.com/laurentS/slowapi](https://github.com/laurentS/slowapi)                               |
| Pillow                    | PIL/BSD-style   | [https://python-pillow.org](https://python-pillow.org)                                                   |
| python-magic              | MIT             | [https://github.com/ahupp/python-magic](https://github.com/ahupp/python-magic)                           |
| aiofiles                  | Apache-2.0      | [https://github.com/Tinche/aiofiles](https://github.com/Tinche/aiofiles)                                 |
| ffmpeg-python             | Apache-2.0      | [https://github.com/kkroening/ffmpeg-python](https://github.com/kkroening/ffmpeg-python)                 |
| httpx                     | BSD-3-Clause    | [https://github.com/encode/httpx](https://github.com/encode/httpx)                                       |
| email-validator           | MIT             | [https://github.com/JoshData/python-email-validator](https://github.com/JoshData/python-email-validator) |
| python-dateutil           | BSD-2-Clause    | [https://github.com/dateutil/dateutil](https://github.com/dateutil/dateutil)                             |
| psutil                    | BSD-3-Clause    | [https://github.com/giampaolo/psutil](https://github.com/giampaolo/psutil)                               |
| gunicorn                  | MIT             | [https://github.com/benoitc/gunicorn](https://github.com/benoitc/gunicorn)                               |

> **FFmpeg Notice:**
> The included FFmpeg binary (installed via Alpine `apk add ffmpeg`) is distributed under the **LGPL 2.1** license.
> The build configuration has been verified to exclude `--enable-gpl` and `--enable-nonfree` flags.

---

## Flutter & Dart Dependencies

| Package                        | License      | Source                                                                                             |
| ------------------------------ | ------------ | -------------------------------------------------------------------------------------------------- |
| flutter (SDK)                  | BSD-3-Clause | [https://github.com/flutter/flutter](https://github.com/flutter/flutter)                           |
| cupertino_icons                | MIT          | [https://pub.dev/packages/cupertino_icons](https://pub.dev/packages/cupertino_icons)               |
| google_fonts                   | Apache-2.0   | [https://pub.dev/packages/google_fonts](https://pub.dev/packages/google_fonts)                     |
| flutter_riverpod               | MIT          | [https://pub.dev/packages/flutter_riverpod](https://pub.dev/packages/flutter_riverpod)             |
| riverpod_annotation            | MIT          | [https://pub.dev/packages/riverpod_annotation](https://pub.dev/packages/riverpod_annotation)       |
| go_router                      | BSD-3-Clause | [https://pub.dev/packages/go_router](https://pub.dev/packages/go_router)                           |
| dio                            | MIT          | [https://pub.dev/packages/dio](https://pub.dev/packages/dio)                                       |
| connectivity_plus              | BSD-3-Clause | [https://pub.dev/packages/connectivity_plus](https://pub.dev/packages/connectivity_plus)           |
| shared_preferences             | BSD-3-Clause | [https://pub.dev/packages/shared_preferences](https://pub.dev/packages/shared_preferences)         |
| flutter_secure_storage         | BSD-3-Clause | [https://pub.dev/packages/flutter_secure_storage](https://pub.dev/packages/flutter_secure_storage) |
| image_picker                   | BSD-3-Clause | [https://pub.dev/packages/image_picker](https://pub.dev/packages/image_picker)                     |
| file_picker                    | MIT          | [https://pub.dev/packages/file_picker](https://pub.dev/packages/file_picker)                       |
| cached_network_image           | MIT          | [https://pub.dev/packages/cached_network_image](https://pub.dev/packages/cached_network_image)     |
| video_player                   | BSD-3-Clause | [https://pub.dev/packages/video_player](https://pub.dev/packages/video_player)                     |
| photo_view                     | MIT          | [https://pub.dev/packages/photo_view](https://pub.dev/packages/photo_view)                         |
| audioplayers                   | MIT          | [https://pub.dev/packages/audioplayers](https://pub.dev/packages/audioplayers)                     |
| mime                           | BSD-3-Clause | [https://pub.dev/packages/mime](https://pub.dev/packages/mime)                                     |
| get_thumbnail_video            | MIT          | [https://pub.dev/packages/get_thumbnail_video](https://pub.dev/packages/get_thumbnail_video)       |
| path_provider                  | BSD-3-Clause | [https://pub.dev/packages/path_provider](https://pub.dev/packages/path_provider)                   |
| intl                           | BSD-3-Clause | [https://pub.dev/packages/intl](https://pub.dev/packages/intl)                                     |
| equatable                      | MIT          | [https://pub.dev/packages/equatable](https://pub.dev/packages/equatable)                           |
| dartz                          | MIT          | [https://pub.dev/packages/dartz](https://pub.dev/packages/dartz)                                   |
| freezed_annotation             | MIT          | [https://pub.dev/packages/freezed_annotation](https://pub.dev/packages/freezed_annotation)         |
| json_annotation                | BSD-3-Clause | [https://pub.dev/packages/json_annotation](https://pub.dev/packages/json_annotation)               |
| url_launcher                   | BSD-3-Clause | [https://pub.dev/packages/url_launcher](https://pub.dev/packages/url_launcher)                     |
| package_info_plus              | BSD-3-Clause | [https://pub.dev/packages/package_info_plus](https://pub.dev/packages/package_info_plus)           |
| flutter_timezone               | MIT          | [https://pub.dev/packages/flutter_timezone](https://pub.dev/packages/flutter_timezone)             |
| fl_chart                       | MIT          | [https://pub.dev/packages/fl_chart](https://pub.dev/packages/fl_chart)                             |
| carousel_slider                | MIT          | [https://pub.dev/packages/carousel_slider](https://pub.dev/packages/carousel_slider)               |
| built_value / built_collection | Apache-2.0   | [https://pub.dev/packages/built_value](https://pub.dev/packages/built_value)                       |
| one_of / one_of_serializer     | Apache-2.0   | [https://pub.dev/packages/one_of](https://pub.dev/packages/one_of)                                 |
| http_parser                    | BSD-3-Clause | [https://pub.dev/packages/http_parser](https://pub.dev/packages/http_parser)                       |
| build_runner                   | MIT          | [https://pub.dev/packages/build_runner](https://pub.dev/packages/build_runner)                     |
| freezed                        | MIT          | [https://pub.dev/packages/freezed](https://pub.dev/packages/freezed)                               |
| json_serializable              | MIT          | [https://pub.dev/packages/json_serializable](https://pub.dev/packages/json_serializable)           |
| riverpod_generator             | MIT          | [https://pub.dev/packages/riverpod_generator](https://pub.dev/packages/riverpod_generator)         |
| built_value_generator          | Apache-2.0   | [https://pub.dev/packages/built_value_generator](https://pub.dev/packages/built_value_generator)   |
| mocktail                       | MIT          | [https://pub.dev/packages/mocktail](https://pub.dev/packages/mocktail)                             |
| integration_test               | BSD-3-Clause | [https://pub.dev/packages/integration_test](https://pub.dev/packages/integration_test)             |
| flutter_lints                  | BSD-3-Clause | [https://pub.dev/packages/flutter_lints](https://pub.dev/packages/flutter_lints)                   |

---

## React Frontend Dependencies

Runtime dependencies of the React frontend (`journiv-backend/frontend`).

| Package                    | License      | Source                                                                                                    |
| -------------------------- | ------------ | ------------------------------------------------------------------------------------------------------- |
| react / react-dom          | MIT          | [https://github.com/facebook/react](https://github.com/facebook/react)                                 |
| @tanstack/react-query      | MIT          | [https://github.com/TanStack/query](https://github.com/TanStack/query)                                 |
| @tanstack/react-router     | MIT          | [https://github.com/TanStack/router](https://github.com/TanStack/router)                               |
| @tanstack/react-virtual    | MIT          | [https://github.com/TanStack/virtual](https://github.com/TanStack/virtual)                             |
| @base-ui/react             | MIT          | [https://github.com/mui/base-ui](https://github.com/mui/base-ui)                                       |
| quill                      | BSD-3-Clause | [https://github.com/slab/quill](https://github.com/slab/quill)                                         |
| recharts                   | MIT          | [https://github.com/recharts/recharts](https://github.com/recharts/recharts)                           |
| yet-another-react-lightbox | MIT          | [https://github.com/igordanchenko/yet-another-react-lightbox](https://github.com/igordanchenko/yet-another-react-lightbox) |
| lucide-react               | ISC          | [https://github.com/lucide-icons/lucide](https://github.com/lucide-icons/lucide)                       |
| date-fns / date-fns-tz     | MIT          | [https://github.com/date-fns/date-fns](https://github.com/date-fns/date-fns)                           |
| react-day-picker           | MIT          | [https://github.com/gpbl/react-day-picker](https://github.com/gpbl/react-day-picker)                   |
| class-variance-authority   | Apache-2.0   | [https://github.com/joe-bell/cva](https://github.com/joe-bell/cva)                                     |
| clsx                       | MIT          | [https://github.com/lukeed/clsx](https://github.com/lukeed/clsx)                                       |
| tailwind-merge             | MIT          | [https://github.com/dcastil/tailwind-merge](https://github.com/dcastil/tailwind-merge)                 |
| idb                        | ISC          | [https://github.com/jakearchibald/idb](https://github.com/jakearchibald/idb)                           |
| @fontsource-variable/\*    | OFL-1.1      | [https://github.com/fontsource/fontsource](https://github.com/fontsource/fontsource)                   |

---

## Fonts

- **Manrope** — Licensed under the [**SIL Open Font License 1.1**](https://scripts.sil.org/OFL).
  Source: [https://fonts.google.com/specimen/Manrope](https://fonts.google.com/specimen/Manrope)

---

## Attribution & Compliance

All third-party software, fonts, and media remain the property of their respective authors and are used under the terms of their licenses.
No modifications were made that affect their original licensing.

Journiv’s original code is licensed under the
[**PolyForm Noncommercial License 1.0.0**](./LICENSE.md),
which applies only to original work created by **Swalab Tech**.

If you believe a license notice is missing or incorrect, please contact: [https://github.com/swalabtech](https://github.com/swalabtech)
