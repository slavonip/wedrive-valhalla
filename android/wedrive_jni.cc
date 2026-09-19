// Отпечаток движка: что именно собрано в этом .so.
//
// Нужен он потому, что патченый движок снаружи НЕОТЛИЧИМ от стокового до первого маршрута через
// границу. Разница — одна строка в Mjolnir и восемь бит региона в метке поиска; ни то, ни другое
// не видно ни по размеру файла, ни по списку символов. Приложение, положившее рядом не тот .so,
// узнает об этом в машине на границе, а не при запуске.
//
// Поэтому библиотека отвечает на три вопроса прямо: сколько регионов она умеет, какой ширины
// поле региона в метке, и совпадают ли размеры меток с теми, на которых всё проверялось.
//
// JNI появится следующим шагом; пока это обычные экспортируемые функции, и их достаточно, чтобы
// доказать, что кросс-сборка дала РАБОЧИЙ движок, а не просто слинковалась.

#include <cstdint>
#include <cstring>

#include <valhalla/baldr/graphid.h>
#include <valhalla/baldr/graphreader.h>
#include <valhalla/sif/edgelabel.h>

extern "C" {

// Сколько независимо собранных регионов способен нести runtime. До расширения было 8, стало 256.
uint32_t wedrive_max_regions() {
  return valhalla::baldr::GraphReader::kWeDriveMaxRegions;
}

// Размеры меток поиска. BDEdgeLabel обязан быть ровно 64 — это кэш-линия, и двунаправленный
// поиск держит миллионы таких меток.
uint32_t wedrive_sizeof_edgelabel() {
  return static_cast<uint32_t>(sizeof(valhalla::sif::EdgeLabel));
}

uint32_t wedrive_sizeof_bdedgelabel() {
  return static_cast<uint32_t>(sizeof(valhalla::sif::BDEdgeLabel));
}

// Проверка инварианта прямо внутри библиотеки: регион переживает и GraphId, и метку.
// Возвращает 0, если всё в порядке, иначе номер провалившейся проверки.
uint32_t wedrive_self_test() {
  using valhalla::baldr::GraphId;

  // 1. GraphId несёт регион и отдаёт неизменными младшие 46 бит.
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

  // 2. Регион переживает set_id — на этом месте он терялся, и это был главный источник потерь.
  GraphId g = plain.with_region(200);
  g.set_id(77);
  if (g.region() != 200 || g.id() != 77) {
    return 3;
  }

  // 3. Размеры меток те же, на которых всё измерялось.
  if (sizeof(valhalla::sif::EdgeLabel) != 40) {
    return 4;
  }
  if (sizeof(valhalla::sif::BDEdgeLabel) != 64) {
    return 5;
  }

  // 4. Регионов должно быть 256, а не 8: иначе собрался движок до расширения.
  if (valhalla::baldr::GraphReader::kWeDriveMaxRegions != 256) {
    return 6;
  }

  return 0;
}

} // extern "C"
