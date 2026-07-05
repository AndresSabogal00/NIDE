# NIDE — Nuclear Information and Data Explorer

> Sucesor web open source de JANIS (NEA), cuyo servicio web será decomisionado en diciembre de 2026.
> 100% gratuito: sin APIs de pago, sin autenticación, sin servicios cloud. Corre local en un MacBook.

---

## 1. Visión

Herramienta web que permite a físicos e ingenieros nucleares explorar, visualizar y **comparar automáticamente** datos nucleares evaluados (secciones eficaces, datos de decaimiento, rendimientos de fisión) de las librerías oficiales ENDF/B, JEFF y JENDL, con superposición de datos experimentales (EXFOR/IAEA) y cálculo de cantidades derivadas estándar. Toda la inteligencia es determinista y está en el código: cero LLMs, cero alucinación, cada número trazable a su evaluación de origen.

---

## 2. Stack tecnológico (todo gratuito y open source)

| Capa | Tecnología | Justificación |
|---|---|---|
| Física / parsing | `openmc` (Python API, módulo `openmc.data`) | Desarrollado por MIT/Argonne. Parsea ENDF-6 y HDF5, reconstruye resonancias, hace Doppler broadening. Validado por la comunidad. Instalable vía pip. |
| Backend | Python 3.11+, FastAPI, uvicorn | API REST rápida, tipada (Pydantic), auto-documentada (Swagger). |
| Cache | Archivos parquet/JSON en disco | Las secciones eficaces se procesan una vez y se cachean. Sin base de datos externa. |
| Frontend | React + Vite, Plotly.js, Tailwind | Plots log-log interactivos de calidad de publicación. |
| Grafos | Cytoscape.js (o d3) | Cadenas de decaimiento como grafos dirigidos interactivos. |
| Datos experimentales | API web de EXFOR (IAEA-NDS) | Gratuita, sin API key. |

## 3. Fuentes de datos (todas oficiales y gratuitas)

1. **ENDF/B-VIII.0 en HDF5** — distribuida por el proyecto OpenMC en https://openmc.org/official-data-libraries/ (descarga directa, ~2 GB con datos de neutrones). Incluye secciones eficaces continuas en energía.
2. **JEFF-3.3 y JENDL-5 en HDF5** — mismas páginas de OpenMC (librerías alternativas para el motor de comparación).
3. **Datos de decaimiento y fission yields** — archivos ENDF-6 de decay/nfy de ENDF/B-VIII (NNDC, Brookhaven: https://www.nndc.bnl.gov/endf/), parseados con `openmc.data.Decay` y `openmc.data.FissionProductYields`.
4. **EXFOR (datos experimentales)** — API web del IAEA Nuclear Data Section (https://nds.iaea.org/exfor/), consultas por nucleido + reacción, retorna JSON/CSV.
5. **Propiedades de nucleidos (masas, vidas medias, abundancias)** — AME2020 / NUBASE2020, archivos de texto públicos.

> Nota: Claude Code descarga estas librerías con `curl`/`wget` durante el setup. La descarga (~2–4 GB total) corre en segundo plano mientras se construye el código; es lo único lento del proyecto.

---

## 4. Estructura del repositorio

```
nide/
├── ARCHITECTURE.md            # este documento
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI app
│   │   ├── core/
│   │   │   ├── library_manager.py    # registro y carga de librerías HDF5
│   │   │   ├── xs_service.py         # extracción de secciones eficaces
│   │   │   ├── comparison_engine.py  # ★ motor de comparación automática
│   │   │   ├── derived_quantities.py # ★ cantidades físicas derivadas
│   │   │   ├── decay_service.py      # datos de decaimiento y cadenas
│   │   │   ├── fission_yields.py     # rendimientos de fisión
│   │   │   └── exfor_client.py       # cliente API EXFOR (con cache local)
│   │   ├── api/routes/        # endpoints REST
│   │   └── models/            # esquemas Pydantic
│   ├── data/                  # librerías HDF5 descargadas (gitignored)
│   ├── cache/                 # resultados procesados (gitignored)
│   ├── scripts/download_data.py      # descarga automática de librerías
│   └── tests/                 # ★ tests de validación física
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── NuclideChart/         # carta de nucleidos interactiva
│   │   │   ├── XSViewer/             # plot log-log de secciones eficaces
│   │   │   ├── ComparisonPanel/      # panel de comparación multi-librería
│   │   │   ├── DecayChainGraph/      # grafo de cadenas de decaimiento
│   │   │   ├── FissionYieldsView/    # distribución de yields (por A, Z)
│   │   │   └── ExportDialog/         # exportación CSV/PNG con citas
│   │   └── api/               # cliente del backend
└── README.md                  # con screenshots y motivación (muerte de JANIS)
```

---

## 5. Módulos clave (especificación)

### 5.1 Library Manager
- Registra librerías disponibles (ENDF/B-VIII.0, JEFF-3.3, JENDL-5) leyendo sus `cross_sections.xml`.
- Carga perezosa (lazy) de nucleidos vía `openmc.data.IncidentNeutron.from_hdf5()`.
- Cache en disco de curvas ya extraídas (energía, sección eficaz) por nucleido/reacción/temperatura.

### 5.2 Cross-Section Service
- Entrada: nucleido (ej. `U235`), reacción (número MT: 18=fisión, 102=captura, 2=elástica, 1=total…), temperatura, librería.
- Salida: grilla de energía (eV) + sección eficaz (barns), lista de MTs disponibles por nucleido.
- Downsampling inteligente para el frontend (max ~5000 puntos preservando resonancias, algoritmo tipo LTTB) con opción de datos completos en exportación.

### 5.3 ★ Comparison Engine (el diferenciador)
Dado nucleido + reacción + lista de librerías:
- Interpola todas las librerías a una grilla de energía común (unión de grillas, interpolación log-log).
- Calcula: **ratio entre evaluaciones**, **diferencia porcentual punto a punto**, y estadísticas por región de energía (térmica < 0.625 eV, epitérmica 0.625 eV–100 keV, rápida > 100 keV).
- **Detección automática de discrepancias**: resalta regiones donde |diff| > umbral configurable (default 5%), y genera un resumen tabular: "ENDF/B y JEFF discrepan hasta X% en la región Y".
- Salida lista para graficar (curvas + banda de discrepancia) y para exportar como reporte CSV.

### 5.4 ★ Derived Quantities
Cantidades estándar que los físicos calculan a mano, ahora a un clic (todas con fórmula documentada en el código):
- Valor térmico a 2200 m/s (0.0253 eV).
- Integral de resonancia: I = ∫ σ(E)/E dE de 0.5 eV a 20 MeV (o límite superior configurable).
- Promedio Maxwelliano a temperatura T (espectro térmico).
- Promedio sobre espectro de fisión de Watt (U-235 térmico, parámetros estándar a=0.988 MeV, b=2.249 MeV⁻¹).
- Estas cantidades se calculan para cada librería → tabla comparativa automática.

### 5.5 Decay Service
- Parseo de sublibrería de decay de ENDF/B-VIII: modos de decaimiento, branching ratios, vidas medias, energías de emisión.
- Construcción recursiva de cadenas de decaimiento como grafo dirigido (nodos=nucleidos, aristas=modos con branching), hasta llegar a nucleidos estables.
- Endpoint que retorna el grafo en JSON para Cytoscape.

### 5.6 Fission Yields
- Yields independientes y acumulativos (térmico/rápido/14 MeV) para U-235, U-238, Pu-239, etc.
- Visualización: distribución por número másico A (la clásica curva de doble joroba) y por Z.

### 5.7 EXFOR Client
- Consulta a la API del IAEA por nucleido + reacción, mapeo de MT a notación EXFOR.
- Cache agresivo en disco (los datos experimentales no cambian).
- Manejo de fallo elegante: si la API no responde, la app funciona igual sin overlay experimental.
- Cada dataset experimental incluye autor, año y referencia bibliográfica (EXFOR los provee) → se muestran en la leyenda del plot.

### 5.8 Export & Citas
- CSV con metadata en header: librería, versión, fecha de acceso, cita oficial de la librería.
- PNG/SVG del plot en calidad de publicación.
- Cada vista muestra la cita de la evaluación de origen (ej. "ENDF/B-VIII.0: Brown et al., Nucl. Data Sheets 148 (2018)").

---

## 6. Frontend — vistas principales

1. **Carta de nucleidos** (home): grilla Z vs N interactiva, coloreable por propiedad (vida media, modo de decaimiento, sección térmica de captura). Clic en nucleido → panel de detalle.
2. **Visor de secciones eficaces**: plot log-log interactivo (zoom, pan, hover con valores), selector de reacciones MT, selector de librerías (multi), toggle de overlay EXFOR.
3. **Panel de comparación**: subplot de ratios/diferencia %, tabla de discrepancias por región, tabla de cantidades derivadas por librería.
4. **Cadenas de decaimiento**: grafo interactivo con vidas medias y branching ratios en las aristas.
5. **Fission yields**: curva de doble joroba, comparación térmico vs rápido.

Diseño: oscuro/científico, tipografía limpia, sin login, todo corre en `localhost`.

---

## 7. Validación física (rigor de nivel doctoral)

Tests automatizados (`pytest`) contra valores de referencia conocidos de la literatura:
- σ_fisión(U-235, térmico) ≈ 585 b · σ_captura(U-238, térmico) ≈ 2.68 b
- σ_captura(H-1, térmico) ≈ 0.332 b · σ_absorción(B-10, térmico) ≈ 3840 b
- Integral de resonancia de captura de U-238 ≈ 275 b
- Vida media Co-60 ≈ 5.27 años; cadena U-238 → ... → Pb-206 completa
- Tolerancia: ±2% (los valores exactos dependen de la evaluación; el test documenta la fuente de cada referencia).

Esto convierte el repo en algo defendible: no solo grafica, **demuestra** que sus números son correctos.

---

## 8. Estándar de código y documentación

- **Comentarios y docstrings a nivel de herramienta open source para científicos**: escritos para un físico nuclear o desarrollador que llega al repo por primera vez, no como explicación tutorial. Documentan el *porqué* físico y las decisiones de diseño (convenciones de unidades, fuente de cada fórmula, referencias bibliográficas, supuestos y límites de validez), no narran lo obvio del código.
- Docstrings estilo NumPy en todos los módulos y funciones públicas, con secciones Parameters/Returns/References.
- Todo en inglés (código, comentarios, docstrings, UI, README): el repo es para la comunidad internacional.
- Unidades explícitas en nombres o docstrings (eV, barns, segundos). Constantes físicas con su fuente (CODATA, evaluación correspondiente).
- Type hints en todo el backend. Código formateado (ruff/black).

---

## 9. Flujo de trabajo — una sola sesión continua

El proyecto se construye completo en una sesión ininterrumpida. El orden siguiente es de dependencias, no de fases; se avanza sin pausas entre ítems y la descarga de datos corre en paralelo desde el inicio:

1. Setup del repo (estructura de la sección 4, git, venv, Vite) y lanzamiento inmediato de la descarga de ENDF/B-VIII.0 en segundo plano (JEFF-3.3 y JENDL-5 se lanzan apenas termine la primera).
2. Library manager + xs_service + endpoints REST básicos.
3. Tests de validación física (sección 7) pasando antes de continuar: el rigor es la prioridad #1.
4. Frontend: visor de secciones eficaces con plot log-log interactivo.
5. Comparison engine + derived quantities (secciones 5.3 y 5.4, el diferenciador) + panel de comparación en frontend.
6. Carta de nucleidos interactiva.
7. Cliente EXFOR con cache y overlay experimental en los plots.
8. Decay chains (grafo Cytoscape) + fission yields.
9. Exportación CSV/PNG con citas.
10. README con screenshots, motivación (muerte de JANIS en dic 2026), instrucciones de instalación en 3 comandos, licencia MIT, y verificación final end-to-end de toda la app.

---

## 10. Restricciones

- **Cero costos**: sin API keys de pago, sin cloud, sin base de datos gestionada. Todo local u APIs públicas gratuitas (IAEA).
- **Sin LLMs en runtime**: toda la funcionalidad es determinista, calculada con física documentada.
- **Trazabilidad total**: cada número mostrado debe poder rastrearse a su librería, versión y evaluación de origen.
- Target: macOS Apple Silicon (M4), Python 3.11+, Node 20+.
