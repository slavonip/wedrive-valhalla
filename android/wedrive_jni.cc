// Мост между приложением и патченым движком.
//
// Здесь две разные вещи, и обе нужны.
//
// ПЕРВАЯ — отпечаток. Патченый .so снаружи НЕОТЛИЧИМ от стокового до первого маршрута через
// границу: разница это одна строка в Mjolnir и восемь бит региона в метке поиска, ни то ни
// другое не видно ни по размеру файла, ни по списку символов. Приложение, положившее рядом не
// тот .so, узнало бы об этом в машине на границе. Поэтому библиотека отвечает прямо: сколько
// регионов умеет, какие размеры меток, переживает ли регион set_id — то самое место, где он
// терялся.
//
// ВТОРАЯ — работа через actor_t, тот же способ встраивания, которым пользуется и
// valhalla-mobile. Конфиг приходит строкой JSON, потому что именно в нём живут wedrive_regions
// и wedrive_portals: приложение собирает его из манифеста, а не хранит зашитым.
//
// Наружу отдаются ДВА действия, и второе не менее обязательно, чем первое: route и
// trace_attributes. На привязке к дорогам в приложении держатся съезды с кругов, знаки
// ограничения скорости, часовой пояс прибытия, счёт пересечённых границ и ленты пробок —
// движок, умеющий только маршрут, выключает их все разом и молча.
//
// Функции без JNIEnv оставлены экспортированными: они не требуют виртуальной машины и потому
// вызываются из CI сразу после сборки, где никакой Java нет. Проверять .so только через
// Android-приложение значило бы узнавать о негодной сборке на сорок минут позже.

#include <cstdint>
#include <exception>
#include <memory>
#include <mutex>
#include <sstream>
#include <string>

#include <jni.h>

#include <boost/property_tree/json_parser.hpp>
#include <boost/property_tree/ptree.hpp>

#include <valhalla/baldr/graphid.h>
#include <valhalla/baldr/graphreader.h>
#include <valhalla/sif/edgelabel.h>
#include <valhalla/tyr/actor.h>

namespace {

struct WeDriveEngine {
  boost::property_tree::ptree config;
  std::unique_ptr<valhalla::tyr::actor_t> actor;
  std::string last_error;
  // actor_t держит воркеров loki/thor/odin с их собственным состоянием и НЕ потокобезопасен.
  // Приложению это не видно: маршрут считается в одной корутине, а привязка лент пробок к
  // дорогам — в другой, и они встречаются на одном actor_t. Без замка это падение процесса,
  // а не неверный ответ, то есть худший вид отказа. Сериализация здесь допустима: долгий
  // маршрут задержит привязку на секунды, и привязка подождёт.
  std::mutex lock;
};

std::string jstr(JNIEnv* env, jstring s) {
  if (s == nullptr) {
    return {};
  }
  const char* p = env->GetStringUTFChars(s, nullptr);
  std::string out(p ? p : "");
  if (p) {
    env->ReleaseStringUTFChars(s, p);
  }
  return out;
}

} // namespace

extern "C" {

// ── ОТПЕЧАТОК: вызывается и из CI, и из приложения ──────────────────────────────────────────

uint32_t wedrive_max_regions() {
  return valhalla::baldr::GraphReader::kWeDriveMaxRegions;
}

uint32_t wedrive_sizeof_edgelabel() {
  return static_cast<uint32_t>(sizeof(valhalla::sif::EdgeLabel));
}

uint32_t wedrive_sizeof_bdedgelabel() {
  return static_cast<uint32_t>(sizeof(valhalla::sif::BDEdgeLabel));
}

// Возвращает 0, если сборка та, что ожидается, иначе номер провалившейся проверки.
uint32_t wedrive_self_test() {
  using valhalla::baldr::GraphId;

  const GraphId plain(3000, 2, 1234);
  for (uint32_t r : {1u, 7u, 8u, 128u, 255u}) {
    const GraphId tagged = plain.with_region(r);
    if (tagged.region() != r) {
      return 1;
    }
    if (tagged.without_region().value != plain.value) {
      return 2;
    }
  }

  // Регион обязан пережить set_id — именно здесь он терялся, и это был главный источник потерь.
  GraphId g = plain.with_region(200);
  g.set_id(77);
  if (g.region() != 200 || g.id() != 77) {
    return 3;
  }

  if (sizeof(valhalla::sif::EdgeLabel) != 40) {
    return 4;
  }
  // Ровно кэш-линия: двунаправленный поиск держит миллионы таких меток.
  if (sizeof(valhalla::sif::BDEdgeLabel) != 64) {
    return 5;
  }
  // 256, а не 8: иначе собрался движок ДО расширения региона.
  if (valhalla::baldr::GraphReader::kWeDriveMaxRegions != 256) {
    return 6;
  }
  return 0;
}

// ── JNI ─────────────────────────────────────────────────────────────────────────────────────

JNIEXPORT jint JNICALL
Java_com_wedrive_data_NativeValhalla_nativeSelfTest(JNIEnv*, jclass) {
  return static_cast<jint>(wedrive_self_test());
}

JNIEXPORT jint JNICALL
Java_com_wedrive_data_NativeValhalla_nativeMaxRegions(JNIEnv*, jclass) {
  return static_cast<jint>(wedrive_max_regions());
}

/**
 * Создаёт движок из конфига. Конфиг приходит СТРОКОЙ, потому что в нём живут wedrive_regions и
 * wedrive_portals — приложение собирает их из манифеста, и зашивать это в .so нельзя: набор
 * установленных стран меняется без пересборки библиотеки.
 *
 * Возвращает дескриптор или 0. Причину отказа отдаёт nativeLastError.
 */
JNIEXPORT jlong JNICALL
Java_com_wedrive_data_NativeValhalla_nativeCreate(JNIEnv* env, jclass, jstring config_json) {
  auto* e = new WeDriveEngine();
  try {
    std::istringstream in(jstr(env, config_json));
    boost::property_tree::read_json(in, e->config);
    // auto_cleanup = TRUE, и прежнее false здесь роняло процесс.
    //
    // Измерено на устройстве 2026-09-20: ПЕРВЫЙ trace_attributes отдаёт 89 КБ атрибутов,
    // ВТОРОЙ на тех же самых точках падает с SIGSEGV в build_trace. География ни при чём —
    // это проверено повтором одного участка, — виновато состояние между запросами.
    // `thor_worker_t::cleanup()` делает `trace.clear()` и `matcher_factory.ClearFullCache()`;
    // без него второй разбор берёт индексы совпадений от ПРЕДЫДУЩЕГО запроса и адресует ими
    // `options.shape()` нового, выходит за границы и пишет по нулю.
    //
    // Прежний довод — «cleanup сбросит кеш тайлов на каждом перестроении» — был неверен по
    // фактам: и thor, и loki трогают читателя только `if (reader->OverCommitted())`, а
    // кеш кандидатов чистят лишь сверх своего порога. Обычный вызов не выбрасывает ничего.
    e->actor = std::make_unique<valhalla::tyr::actor_t>(e->config, true);
  } catch (const std::exception& ex) {
    // Не бросаем наружу: исключение через границу JNI — это падение процесса, а не сообщение.
    e->last_error = ex.what();
    e->actor.reset();
  } catch (...) {
    e->last_error = "неизвестная ошибка при создании движка";
    e->actor.reset();
  }
  if (!e->actor) {
    // Объект оставляем жить, чтобы приложение успело прочитать причину; освободит nativeDestroy.
    return reinterpret_cast<jlong>(e);
  }
  return reinterpret_cast<jlong>(e);
}

JNIEXPORT jboolean JNICALL
Java_com_wedrive_data_NativeValhalla_nativeIsReady(JNIEnv*, jclass, jlong handle) {
  auto* e = reinterpret_cast<WeDriveEngine*>(handle);
  return (e && e->actor) ? JNI_TRUE : JNI_FALSE;
}

JNIEXPORT jstring JNICALL
Java_com_wedrive_data_NativeValhalla_nativeLastError(JNIEnv* env, jclass, jlong handle) {
  auto* e = reinterpret_cast<WeDriveEngine*>(handle);
  return env->NewStringUTF(e ? e->last_error.c_str() : "нет дескриптора");
}

/**
 * Считает маршрут. Запрос и ответ — JSON, тот же формат, что у valhalla_service, поэтому всё,
 * что проверено на десктопе, проверено и здесь.
 *
 * Возвращает null при отказе; причина — в nativeLastError.
 */
JNIEXPORT jstring JNICALL
Java_com_wedrive_data_NativeValhalla_nativeRoute(JNIEnv* env, jclass, jlong handle,
                                                 jstring request_json) {
  auto* e = reinterpret_cast<WeDriveEngine*>(handle);
  if (!e || !e->actor) {
    return nullptr;
  }
  const std::string request = jstr(env, request_json);
  try {
    std::lock_guard<std::mutex> guard(e->lock);
    const std::string out = e->actor->route(request);
    return env->NewStringUTF(out.c_str());
  } catch (const std::exception& ex) {
    e->last_error = ex.what();
  } catch (...) {
    e->last_error = "неизвестная ошибка при построении маршрута";
  }
  return nullptr;
}

/**
 * Привязывает точки к дорогам и отдаёт атрибуты пройденных рёбер — `trace_attributes`.
 *
 * **Почему это НЕ довесок к маршруту, а вторая половина работы движка.** На нём в приложении
 * держатся четыре вещи сразу: номер съезда с круга (по топологии пройденных рёбер), знак
 * ограничения скорости, часовой пояс точки прибытия и число пересечённых границ — плюс
 * привязка лент пробок к нашим же дорогам. Отдать наружу один только `route` значит молча
 * выключить их все: приложение продолжит ехать, но перестанет знать, где съезжать.
 *
 * **Отдельный риск, который здесь и проверяется.** Meili не пользуется Thor: у него своя
 * выборка кандидатов, своё расширение и своя модель стоимости, и ни один из патчей маршрута
 * его не касался (патчи 47–64 сделаны отдельно). Поэтому «маршрут через границу построился»
 * ничего не говорит о том, что через ту же границу пройдёт привязка.
 *
 * Возвращает null при отказе; причина — в nativeLastError.
 */
JNIEXPORT jstring JNICALL
Java_com_wedrive_data_NativeValhalla_nativeTraceAttributes(JNIEnv* env, jclass, jlong handle,
                                                           jstring request_json) {
  auto* e = reinterpret_cast<WeDriveEngine*>(handle);
  if (!e || !e->actor) {
    return nullptr;
  }
  const std::string request = jstr(env, request_json);
  try {
    std::lock_guard<std::mutex> guard(e->lock);
    const std::string out = e->actor->trace_attributes(request);
    return env->NewStringUTF(out.c_str());
  } catch (const std::exception& ex) {
    e->last_error = ex.what();
  } catch (...) {
    e->last_error = "неизвестная ошибка при привязке к дорогам";
  }
  return nullptr;
}

JNIEXPORT void JNICALL
Java_com_wedrive_data_NativeValhalla_nativeDestroy(JNIEnv*, jclass, jlong handle) {
  delete reinterpret_cast<WeDriveEngine*>(handle);
}

} // extern "C"
