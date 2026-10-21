# Guía de uso de la ICD API — edición en español

> **Documento de referencia** para integrar la ICD API de la Organización Mundial de la Salud
> (`https://id.who.int/`) con la **edición en español** del ICD-11.
> Todo lo que sigue está verificado contra la especificación OpenAPI publicada por la OMS
> (`https://id.who.int/swagger/v2/swagger.json`, OpenAPI 3.0.1, 21 endpoints) y contra la
> documentación oficial en `https://icd.who.int/docs/icd-api/APIDoc-Version2/`.

---

## Resumen rápido

Si solo quieres la versión mínima que funciona:

```bash
# 1. Credenciales (las obtienes en https://icd.who.int/icdapi -> "View API access key")
export ICD_CLIENT_ID="tu-client-id"
export ICD_CLIENT_SECRET="tu-client-secret"

# 2. Token OAuth 2.0 (dura ~1 hora)
TOKEN=$(curl -sS -X POST https://icdaccessmanagement.who.int/connect/token \
  -u "$ICD_CLIENT_ID:$ICD_CLIENT_SECRET" \
  -d grant_type=client_credentials \
  -d scope=icdapi_access \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')

# 3. Buscar "cólera" en la ICD-11 MMS en español
curl -sS "https://id.who.int/icd/release/11/2025-01/mms/search?q=colera" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/json" \
  -H "Accept-Language: es" \
  -H "API-Version: v2"
```

Las cuatro cabeceras de la llamada son **obligatorias**: sin `API-Version: v2` la API responde en
formato v1; sin `Accept-Language: es` te devolverá el texto en inglés; sin `Accept: application/json`
no negociará el formato correcto; y sin `Authorization: Bearer <token>` recibirás un `401`.

---

<a id="indice"></a>

## Índice

1. [Antes de empezar](#antes-de-empezar)
2. [Autenticación OAuth 2.0](#autenticacion)
3. [Cabeceras obligatorias](#cabeceras)
4. [La edición española del ICD-11](#edicion-espanola)
5. [Mapa de endpoints](#endpoints)
6. [Recetas prácticas](#recetas)
7. [Referencia de parámetros](#parametros)
8. [Formato de respuesta](#respuesta)
9. [Errores y códigos de estado](#errores)
10. [Buenas prácticas](#practicas)
11. [Despliegue local](#despliegue-local)
12. [Recursos](#recursos)
13. [Apéndices](#apendices)

---

<a id="antes-de-empezar"></a>

## 1. Antes de empezar

### 1.1 Qué es la ICD API

La ICD API es una API REST que da acceso programático a la **Clasificación Internacional de
Enfermedades** de la OMS. No es un "buscador" suelto: es la fuente de verdad que alimenta el
ICD-11 Browser, la herramienta de codificación y el motor DORIS de la OMS, y expone exactamente
la misma información en formato JSON-LD.

Datos clave:

| Dato | Valor |
| --- | --- |
| URL base | `https://id.who.int/` |
| Versión de la API | 2.6 (enero de 2026) |
| Cabecera de versión | `API-Version: v2` (solo el número mayor) |
| Autenticación | OAuth 2.0, *client credentials* |
| Endpoint de token | `https://icdaccessmanagement.who.int/connect/token` |
| Ámbito (scope) | `icdapi_access` |
| Formato de datos | JSON-LD (`application/json` o `application/ld+json`) |
| Duración del token | ~1 hora |

La versión 2 es **compatible hacia atrás** con la 2.x: el código escrito para 2.x no necesita
cambios. Lo único que hay que hacer es enviar la cabecera `API-Version: v2`, porque sin ella la
API responde con el formato de la versión 1.

RDF/XML, que sí estaba soportado en las primeras versiones, está **deprecado desde la 2.3**.

### 1.2 Alcance: Fundamento, linearizaciones e ICD-10

La API expone tres cosas distintas que se confunden con frecuencia. Distinguirlas es el paso más
importante antes de escribir código:

| Capa | Qué es | Dónde vive en la API | ¿Tiene códigos? |
| --- | --- | --- | --- |
| **Fundamento** (*Foundation Component*) | El universo completo de la OMS-FIC: enfermedades, trastornos, lesiones, signos, descripciones funcionales, intervenciones y códigos de extensión. Puede haber **varios padres** para la misma entidad. | `/icd/entity/...` | No |
| **Linearizaciones** (listas tabulares) | Un subconjunto del Fundamento con una finalidad concreta, donde las entidades son **mutuamente excluyentes** y tienen **un solo padre**. | `/icd/release/11/...` | Sí |
| **ICD-10** | Las ediciones clásica de la ICD-10. | `/icd/release/10/...` | Sí |

Las dos linearizaciones disponibles son:

- **`mms`** — ICD-11 para Mortalidad y Morbilidad (MMS). Es la que necesitas **siempre que
  necesites códigos y la estructura tal y como aparece en la ICD-11 publicada**.
- **`icf`** — Clasificación Internacional del Funcionamiento, la Discapacidad y la Salud (ICF).

> **Aviso importante.** Si estás construyendo una herramienta que necesita códigos ICD-11 con la
> estructura que muestra la ICD-11 publicada (`https://icd.who.int/browse11`), tienes que usar los
> endpoints de **linearización** con `linearizationname=mms`. El Fundamento no tiene códigos ni
> excluye entidades entre sí: no sirve para codificar.

### 1.3 Requisitos previos

- Una cuenta en `https://icd.who.int/icdapi` (el registro es gratuito).
- Las credenciales `clientId` y `clientSecret`, que obtienes con el enlace
  **"View API access key"** una vez dentro del portal.
- Un cliente HTTP cualquiera. Todos los ejemplos de esta guía usan `curl`, Python y JavaScript.

---

<a id="autenticacion"></a>

## 2. Autenticación OAuth 2.0

### 2.1 Obtener las credenciales

1. Regístrate en `https://icd.who.int/icdapi` mediante el enlace **[Register]**.
2. Inicia sesión en el portal.
3. Pulsa **"View API access key"**. Verás tu `clientid` y `clientsecret`.
4. Puedes crear y revocar varios clientes por usuario, pero para un uso normal uno basta.

**No pongas el `clientsecret` en el código fuente ni en un repositorio.** Léelo de un gestor de
secretos, de variables de entorno o de un almacén cifrado.

### 2.2 Solicitar el token

La API usa OAuth 2.0 con el tipo de concesión *client credentials* (RFC 6749). La petición es un
`POST` a `https://icdaccessmanagement.who.int/connect/token` con:

- **Autenticación HTTP Basic** con `clientId:clientSecret`.
- `grant_type=client_credentials`.
- `scope=icdapi_access`.

```bash
# Solicitar el token y guardarlo en una variable
curl -sS -X POST https://icdaccessmanagement.who.int/connect/token \
  -u "$ICD_CLIENT_ID:$ICD_CLIENT_SECRET" \
  -d grant_type=client_credentials \
  -d scope=icdapi_access
```

La respuesta es un JSON con el token y su caducidad:

```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiIsImtpZCI6...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "icdapi_access"
}
```

### 2.3 Ciclo de vida del token

El token es válido **aproximadamente una hora**. En la práctica:

- **Cachéalo** y reutilízalo entre llamadas. Pedir un token por cada consulta duplica tu tráfico y
  te hace más susceptible de que laOMS limite tu cuenta.
- **Guarda `expires_in`** y renueva antes de que caduque (por ejemplo, a los 50 minutos).
- **Trata un `401` como señal de token caducado**: pide uno nuevo y repite la petición una sola vez.
  Un `401` casi nunca significa que el recurso no existe.

### 2.4 Ejemplos completos

**Python (cliente con caché de token):**

```python
"""Cliente mínimo de la ICD API en español, con caché del token OAuth 2.0."""

import time
import urllib.parse
import urllib.request
import base64
import json
import os

TOKEN_URL = "https://icdaccessmanagement.who.int/connect/token"
API_BASE = "https://id.who.int"
SCOPE = "icdapi_access"


class IcdApiClient:
    """Cliente de la ICD API con renovación automática del token."""

    def __init__(self, client_id: str, client_secret: str, language: str = "es"):
        self.client_id = client_id
        self.client_secret = client_secret
        self.language = language
        self._token = None
        self._expires_at = 0.0

    def _fetch_token(self) -> str:
        credentials = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode("utf-8")
        ).decode("ascii")
        body = urllib.parse.urlencode(
            {"grant_type": "client_credentials", "scope": SCOPE}
        ).encode("ascii")
        request = urllib.request.Request(
            TOKEN_URL,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
        self._expires_at = time.time() + int(payload.get("expires_in", 3600)) - 60
        self._token = payload["access_token"]
        return self._token

    def token(self) -> str:
        if not self._token or time.time() >= self._expires_at:
            return self._fetch_token()
        return self._token

    def get(self, path: str, params: dict | None = None) -> dict:
        url = f"{API_BASE}{path}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        for attempt in (1, 2):
            request = urllib.request.Request(
                url,
                headers={
                    "Authorization": f"Bearer {self.token()}",
                    "Accept": "application/json",
                    "Accept-Language": self.language,
                    "API-Version": "v2",
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    return json.load(response)
            except urllib.error.HTTPError as error:
                if error.code == 401 and attempt == 1:
                    self._token = None  # fuerza la renovación y reintenta
                    continue
                raise


if __name__ == "__main__":
    client = IcdApiClient(
        os.environ["ICD_CLIENT_ID"], os.environ["ICD_CLIENT_SECRET"]
    )
    resultado = client.get(
        "/icd/release/11/2025-01/mms/search", {"q": "diabetes mellitus tipo 2"}
    )
    for entidad in resultado.get("destinationEntities", []):
        print(entidad.get("code"), "-", entidad.get("title"))
```

**JavaScript (Node.js 18+, `fetch` nativo):**

```javascript
// Cliente de la ICD API en español con caché del token.
const TOKEN_URL = "https://icdaccessmanagement.who.int/connect/token";
const API_BASE = "https://id.who.int";
const SCOPE = "icdapi_access";

export class IcdApiClient {
  constructor(clientId, clientSecret, language = "es") {
    this.clientId = clientId;
    this.clientSecret = clientSecret;
    this.language = language;
    this.token = null;
    this.expiresAt = 0;
  }

  async getToken() {
    const credentials = Buffer.from(`${this.clientId}:${this.clientSecret}`).toString("base64");
    const response = await fetch(TOKEN_URL, {
      method: "POST",
      headers: {
        Authorization: `Basic ${credentials}`,
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: new URLSearchParams({
        grant_type: "client_credentials",
        scope: SCOPE,
      }),
    });
    if (!response.ok) {
      throw new Error(`No se pudo obtener el token: ${response.status} ${await response.text()}`);
    }
    const payload = await response.json();
    this.token = payload.access_token;
    this.expiresAt = Date.now() + (payload.expires_in ?? 3600) * 1000 - 60000;
    return this.token;
  }

  async get(path, params = {}) {
    const url = new URL(path, API_BASE);
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null) {
        url.searchParams.set(key, String(value));
      }
    }
    for (let attempt = 1; attempt <= 2; attempt += 1) {
      if (!this.token || Date.now() >= this.expiresAt) {
        await this.getToken();
      }
      const response = await fetch(url, {
        headers: {
          Authorization: `Bearer ${this.token}`,
          Accept: "application/json",
          "Accept-Language": this.language,
          "API-Version": "v2",
        },
      });
      if (response.status === 401 && attempt === 1) {
        this.token = null;
        continue;
      }
      if (!response.ok) {
        throw new Error(`Error ${response.status}: ${await response.text()}`);
      }
      return response.json();
    }
    throw new Error("No se pudo autenticar la petición");
  }
}
```

---

<a id="cabeceras"></a>

## 3. Cabeceras obligatorias

### 3.1 Las cuatro cabeceras

| Cabecera | Valor | Obligatoria | Para qué sirve |
| --- | --- | --- | --- |
| `Authorization` | `Bearer <access_token>` | Sí | Autenticación OAuth 2.0. Sin ella: `401`. |
| `Accept` | `application/json` o `application/ld+json` | Sí | Selecciona el formato JSON-LD. |
| `Accept-Language` | `es` | Sí | **Selecciona la versión en español** del texto. |
| `API-Version` | `v2` | Sí | Selecciona la versión 2 de la API. Solo el número mayor. |

`Accept-Language` es la cabecera que hace todo el trabajo de la edición en español. Acepta códigos
ISO 639-1 (`en`, `es`, `fr`, `pt`, `zh`…) y también admitirá prioridades al estilo
`es,es-ES;q=0.9,en;q=0.8`, aunque lo sencillo y lo que la OMS documenta es un único código.

Los **resultados de búsqueda** se devuelven en JSON plano, no en JSON-LD, aunque se pida
`application/ld+json`. No es un error: es el comportamiento documentado de la API.

### 3.2 HTTPS y URI de la clasificación

Todas las comunicaciones van cifradas: **solo se admite `https`**. Las peticiones `http` se
redirigen automáticamente, pero la OMS recomienda llamar directamente a `https` porque funciona más
rápido (ahorras el salto de redirección).

Hay un detalle que sorprende la primera vez: **las URI de las entidades de la clasificación
llevan `http`**, porque son identificadores estables y no URLs de la API. Por ejemplo, la URI del
Fundamento para el cólera es `http://id.who.int/icd/entity/257068234`. Esa misma URI **es** el
endpoint de la API que devuelve la ficha de esa entidad.

Regla práctica: **reescribe `http://id.who.int/...` a `https://id.who.int/...` antes de llamar**.
No lo hagas con una sustitución ciega sobre datos que vengan de la API: hazlo solo en la capa que
construye URLs de peticiones.

---

<a id="edicion-espanola"></a>

## 4. La edición española del ICD-11

Esta es la parte específica de esta guía.

### 4.1 Código de idioma

El español se identifica con el código **ISO 639-1 `es`**. Se usa en la cabecera `Accept-Language`
y es lo que devuelve la API en el campo `@language` de cada texto traducible.

| Idioma | Código | Idioma | Código |
| --- | --- | --- | --- |
| Árabe | `ar` | Portugués | `pt` |
| Armenio | `hy` | Ruso | `ru` |
| Chino | `zh` | Eslovaco | `sk` |
| Checo | `cs` | **Español** | **`es`** |
| Neerlandés | `nl` | Sueco | `sv` |
| Inglés | `en` | Tailandés | `th` |
| Estonio | `et` | Turco | `tr` |
| Finlandés | `fi` | Turcomeno | `tk` |
| Francés | `fr` | Ucraniano | `uk` |
| Alemán | `de` | Uzbeko | `uz` |
| Italiano | `it` | Japonés | `ja` |
| Kazajo | `kk` | Coreano | `ko` |
| Latín | `la` | Persa | `fa` |
| Mongolio | `mn` | Polaco | `pl` |

### 4.2 En qué versiones hay español

El soporte del español **depende de la versión y de la clasificación**. Esta tabla reproduce la
tabla oficial de *Supported Classifications* (`https://icd.who.int/docs/icd-api/SupportedClassifications/`):

| `releaseId` | Fundamento | ICD-11 MMS (idiomas) | ICF (idiomas) |
| --- | --- | --- | --- |
| `2026-01` | ✔ | Árabe, Chino, Checo, Inglés, Francés, Alemán<sup>2</sup>, Kazajo, Latín<sup>1</sup>, Portugués, Ruso, Eslovaco, **Español**, Sueco, Turco, Uzbeko | Armenio, Chino, Checo, Inglés, Estonio, Finlandés, Francés, Italiano, Mongolio, Portugués, Ruso, Eslovaco, **Español**, Turco, Ucraniano |
| `2025-01` | ✔ | Árabe, Chino, Checo, Inglés, Francés, Kazajo, Latín<sup>1</sup>, Portugués, Ruso, Eslovaco, **Español**, Turco, Uzbeko | Chino, Checo, Inglés, Francés, **Español**, Turco |
| `2024-01` | ✔ | Árabe, Chino, Checo, Inglés, Francés, Portugués, Ruso, **Español**, Turco, Uzbeko | Checo, Inglés, Turco |
| `2023-01` | ✔ | Árabe, Chino, Inglés, Francés, Ruso, **Español**, Turco | — |
| `2022-02` | ✔ | Árabe, Chino, Inglés, Francés, **Español** | — |
| `2021-05` | ✔ | Árabe, Chino, Inglés, **Español** | — |
| `2020-09` | ✔ | Árabe, Inglés, **Español** | — |
| `2019-04` | ✔ | Inglés | — |
| `2018` | ✔ | Inglés | — |

<sup>1</sup> La versión en **latino** contiene únicamente los títulos de la ICD-11.
<sup>2</sup> El **alemán** está disponible como *prerelease* en la versión 2026-01.

Conclusiones prácticas que ahorran mucho tiempo:

- **El español en MMS existe desde la versión `2020-09`.** Las versiones `2019-04` y `2018` solo
  tienen inglés. Si necesitas una versión muy antigua, no hay texto en español disponible.
- **El español en ICF existe desde la versión `2025-01`.** En `2024-01` la ICF solo está en checo,
  inglés y turco. Antes de `2025-01` la ICF no tiene traducción al español (y en `2023-01` y
  anteriores la ICF ni siquiera está disponible en la API).
- **El Fundamento está disponible en todas las versiones**, pero la traducción puede ser
  **parcial**: la OMS advierte que si un idioma no está disponible en todas las clasificaciones,
  su traducción en el Fundamento también puede estar incompleta. No des por hecho que todo el
  Fundamento está traducido al español.
- **La ICD-10 no tiene versión en español.** Las ediciones ICD-10 disponibles (2019, 2016, 2010 y
  2008) están solo en inglés, y la de 2008 además en francés.

### 4.3 Verificar los idiomas disponibles en vivo

No te fíes de una tabla: la API te dice exactamente qué hay en cada versión. Desde la versión 2.6
el endpoint de primer nivel del Fundamento y los de linearización incluyen información de idiomas
y versiones.

**Idiomas disponibles en la ICF de la versión 2026-01** (con `es` entre ellos):

```bash
curl -sS "https://id.who.int/icd/release/11/2026-01/icf" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/json" \
  -H "Accept-Language: es" \
  -H "API-Version: v2"
```

En la respuesta encontrarás dos campos clave:

| Campo | Significado |
| --- | --- |
| `availableLanguages` | Todos los idiomas disponibles para esa linearización, **incluidos los que están en prerelease**. |
| `prereleaseLanguages` | Subconjunto de los anteriores: los que aún no son una traducción estable. |

En el Fundamento (`/icd/entity`) hay dos campos equivalentes:

| Campo | Significado |
| --- | --- |
| `availableLanguages` | Todos los idiomas disponibles en **alguna** linearización (no solo en la que te interesa). |
| `allReleases` | Todas las versiones desplegadas en la API. |
| `supportedLinearizations` | Las linearizaciones disponibles a partir de ese Fundamento. |

> Si `es` **no** aparece en `availableLanguages` de la linearización que te interesa, esa
> combinación de versión e idioma no existe. Cambia de `releaseId` o de linearización.

### 4.4 Consideraciones al buscar en español

- **Los términos de búsqueda van en el idioma que quieres que se busquen.** La API busca en los
  títulos, sinónimos y nombres completamente especificados de la versión del idioma solicitado.
  Buscar `"diabetes mellitus tipo 2"` con `Accept-Language: es` encuentra la entidad española;
  con `Accept-Language: en` buscarías la entidad inglesa (que puede ser otra URI).
- **Las entidades no se traducen "en el sitio": son entidades distintas por idioma.** El título
  español y el inglés de una misma categoría suelen tener **URIs distintas** en la API. Si guardas
  URIs, guárdalas junto con el idioma con el que las obtuviste.
- **Tildes, `ñ` y diacríticos.** La API no normaliza de forma magic: si el texto indexado en
  español lleva tilde (`cólera`) y tú envías `colera`, el resultado puede no aparecer. Prueba
  ambas formas, o usa el comodín `%` al final de la palabra (ver §7).
- **Los sinónimos en español están indexados.** En la ICD-11 MMS en español, muchas entidades
  tienen sinónimos traducidos; buscar un término habitual de tu país tiene más probabilidades de
  acertar que buscar el título oficial.
- **Las definiciones también están en español** cuando la traducción de la versión lo cubre. Para
  buscarlas hay que desactivar el modo de codificación médica (ver `medicalCodingMode` en §7).

---

<a id="endpoints"></a>

## 5. Mapa de endpoints

La API expone **21 endpoints**. Todos aceptan `GET`, salvo los de búsqueda, que también admiten
`POST` (útil cuando la consulta es demasiado larga para una `GET`, que tiene un límite de 2 KB), y
DORIS/CODEDIT, que aceptan ambos métodos con formatos de entrada distintos.

### 5.1 Fundamento

| Método | Ruta | Qué devuelve |
| --- | --- | --- |
| GET | `/icd/entity` | Información del Fundamento: versión, versiones disponibles, idiomas y linearizaciones soportadas. |
| GET | `/icd/entity/{id}` | Ficha de una entidad concreta del Fundamento. |
| GET | `/icd/entity/autocode` | Mejor coincidencia (código y URI) para un texto diagnóstico. |
| GET, POST | `/icd/entity/search` | Búsqueda en el Fundamento. |

### 5.2 ICD-11 (linearizaciones)

| Método | Ruta | Qué devuelve |
| --- | --- | --- |
| GET | `/icd/release/11/{linearizationname}` | Información de la linearización y lista de versiones disponibles. |
| GET | `/icd/release/11/{linearizationname}/{id}` | URI de la entidad en cada versión disponible. |
| GET | `/icd/release/11/{linearizationname}/{id}/{residual}` | URI de la categoría residual en cada versión. |
| GET | `/icd/release/11/{releaseId}/{linearizationname}` | Información de la versión publicada y lista de capítulos. |
| GET | `/icd/release/11/{releaseId}/{linearizationname}/{id}` | Ficha de una entidad de la linearización. |
| GET | `/icd/release/11/{releaseId}/{linearizationname}/{id}/{residual}` | Ficha de una categoría residual (`other` o `unspecified`). |
| GET | `/icd/release/11/{releaseId}/{linearizationname}/autocode` | Autocodificación dentro de la linearización. |
| GET | `/icd/release/11/{releaseId}/{linearizationname}/codeinfo/{code}` | Ficha de un código o combinación de códigos. |
| GET | `/icd/release/11/{releaseId}/{linearizationname}/describe` | Describe un código, una URI o una combinación de ambos. |
| GET | `/icd/release/11/{releaseId}/{linearizationname}/lookup` | Localiza una entidad del Fundamento dentro de la linearización. |
| GET, POST | `/icd/release/11/{releaseId}/{linearizationname}/search` | Búsqueda en la linearización (MMS, ICF). |

`{linearizationname}` es `mms` o `icf`. `{residual}` es `other` (otra residual especificada) o
`unspecified` (residual no especificada); en ambos casos el `{id}` es **el mismo que el de la
entidad padre**.

### 5.3 CODEDIT y DORIS

| Método | Ruta | Qué devuelve |
| --- | --- | --- |
| GET, POST | `/icd/release/11/{releaseId}/codedit` | Comprueba la completitud y la coherencia de un certificado de defunción. |
| GET, POST | `/icd/release/11/{releaseId}/doris` | Calcula la causa subyacente de muerte según las reglas de la ICD. |

Ambos, consulta la sección [Recursos](#recursos) para el detalle de los campos de entrada y salida.

### 5.4 ICD-10

| Método | Ruta | Qué devuelve |
| --- | --- | --- |
| GET | `/icd/release/10` | Versiones de ICD-10 disponibles. |
| GET | `/icd/release/10/{code}` | Versiones disponibles para una categoría concreta. |
| GET | `/icd/release/10/{releaseId}` | Información de la versión publicada y sus capítulos. |
| GET | `/icd/release/10/{releaseId}/{code}` | Ficha de una categoría y sus subcategorías. |

> **Limitación importante.** En los endpoints de ICD-10 **no hay búsqueda**. La funcionalidad es
> deliberadamente reducida. Y recuerda: **ICD-10 no está disponible en español**.

---

<a id="recetas"></a>

## 6. Recetas prácticas

### 6.1 Buscar un término en español

```bash
# Buscar "cólera" en la ICD-11 MMS, versión 2025-01, en español
curl -sS -G "https://id.who.int/icd/release/11/2025-01/mms/search" \
  --data-urlencode "q=cólera" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/json" \
  -H "Accept-Language: es" \
  -H "API-Version: v2"
```

Variables útiles:

- `q` — el texto a buscar. Un `%` al final de una palabra actúa de comodín para esa palabra.
- `medicalCodingMode=true` (por defecto) — solo devuelve entidades **con código**, que es lo que
  quieres al codificar.
- `flatResults=true` — devuelve una lista plana de coincidencias en lugar de un árbol.
- `useFlexisearch=true` — búsqueda laxa: los resultados no tienen por qué contener *todas* las
  palabras. Úsalo solo cuando la búsqueda normal no devuelve nada.
- `chapterFilter` — restringe a capítulos concretos, por ejemplo `01;02;21`.

```bash
# Búsqueda laxa, solo capítulo 01 (enfermedades infecciosas), con comodín
curl -sS -G "https://id.who.int/icd/release/11/2025-01/mms/search" \
  --data-urlencode "q=influenza%" \
  --data-urlencode "chapterFilter=01" \
  --data-urlencode "useFlexisearch=true" \
  --data-urlencode "medicalCodingMode=true" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/json" \
  -H "Accept-Language: es" \
  -H "API-Version: v2"
```

Cuando la consulta no cabe en 2 KB, usa `POST`:

```bash
# El mismo endpoint acepta POST con los mismos parámetros
curl -sS -X POST "https://id.who.int/icd/release/11/2025-01/mms/search" \
  --data-urlencode "q=neumonía adquirida en la comunidad" \
  --data-urlencode "medicalCodingMode=true" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/json" \
  -H "Accept-Language: es" \
  -H "API-Version: v2"
```

### 6.2 Obtener la ficha de una entidad

```bash
# Ficha de una entidad de la ICD-11 MMS en español, con sus ancestros
curl -sS "https://id.who.int/icd/release/11/2025-01/mms/1466586723" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/json" \
  -H "Accept-Language: es" \
  -H "API-Version: v2"
```

El parámetro `include` añade propiedades que no vienen por defecto. Admite una lista separada por
comas:

```bash
# Incluir ancestros, descendientes y criterios diagnósticos
curl -sS "https://id.who.int/icd/release/11/2025-01/mms/1466586723?include=ancestor,descendant,diagnosticCriteria" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/json" \
  -H "Accept-Language: es" \
  -H "API-Version: v2"
```

### 6.3 Describir un código

```bash
# Describir el código 1A00 (cólera) en la MMS en español
curl -sS -G "https://id.who.int/icd/release/11/2025-01/mms/describe" \
  --data-urlencode "code=1A00" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/json" \
  -H "Accept-Language: es" \
  -H "API-Version: v2"
```

### 6.4 Postcoordinación

La postcoordinación combina un código base («tallo», *stem*) con uno o varios ejes de extensión.
Los caracteres `&` y `/` **deben ir codificados en la URL** (`%26` y `%2F`).

```bash
# Combinación postcoordinada: infección del tracto urinario + Escherichia coli
# (el & va codificado como %26)
curl -sS "https://id.who.int/icd/release/11/2025-01/mms/codeinfo/GC08%26XN62R" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/json" \
  -H "Accept-Language: es" \
  -H "API-Version: v2"
```

Dos modificadores que necesitarás a menudo:

- `flexiblemode=true` — devuelve resultado aunque algunos valores postcoordinados no estén en los
  conjuntos de valores predefinidos. Los que no se pueden asignar a un eje van bajo
  `otherPostcoordination`.
- `convertToTerminalCodes=true` — convierte los códigos a los terminales (hojas del árbol),
  normalmente sustituyéndolos por la residual no especificada del padre.

`describe` va un paso más allá y puede **simplificar** la combinación: si existe una entidad
precoordinada equivalente, la devuelve.

```bash
# Simplificar la combinación y describirla
curl -sS -G "https://id.who.int/icd/release/11/2025-01/mms/describe" \
  --data-urlencode "code=GC08&XN62R" \
  --data-urlencode "simplify=true" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/json" \
  -H "Accept-Language: es" \
  -H "API-Version: v2"
```

### 6.5 Localizar una entidad del Fundamento en la MMS

```bash
# ¿Dónde está codificada esta entidad del Fundamento dentro de la MMS?
curl -sS -G "https://id.who.int/icd/release/11/2025-01/mms/lookup" \
  --data-urlencode "foundationUri=http://id.who.int/icd/entity/257068234" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/json" \
  -H "Accept-Language: es" \
  -H "API-Version: v2"
```

El `lookup` es la herramienta clave para **traducir entre el Fundamento y la tabla**. Devuelve la
entidad de la linearización si la entidad del Fundamento está incluida y tiene código; si está
incluida pero es un grupo sin código, devuelve la residual no especificada de ese grupo; y si no
está incluida, devuelve la entidad a la que se agrega.

### 6.6 Autocodificación de un texto diagnóstico en español

```bash
# Texto diagnóstico libre en español -> mejor coincidencia con su código
curl -sS -G "https://id.who.int/icd/release/11/2025-01/mms/autocode" \
  --data-urlencode "searchText=diabetes mellitus tipo 2 no controlado" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/json" \
  -H "Accept-Language: es" \
  -H "API-Version: v2"
```

La respuesta incluye `theCode` (código encontrado), `matchScore` (de 0 a 1), `matchLevel` (el grado
de coincidencia) y `matchType` (la propiedad donde se encontró la coincidencia: `Title`,
`Synonym`…). **Usa `matchScore` como umbral de confianza en tu flujo**: una coincidencia por
debajo de tu umbral debería ir a revisión manual.

### 6.7 Flujo completo: del texto diagnóstico al código verificado

```python
"""Flujo completo: texto diagnóstico en español -> código ICD-11 verificado."""

import os

from icd_client import IcdApiClient  # el cliente de la sección 2.4


def diagnostic_to_code(client: IcdApiClient, texto: str, release_id: str = "2025-01") -> dict:
    """Busca un término, autocompleta y verifica el código resultante."""
    base = f"/icd/release/11/{release_id}/mms"

    # 1. Autocodificación: texto libre -> mejor candidato
    auto = client.get(f"{base}/autocode", {"searchText": texto})
    if auto.get("matchScore", 0) < 0.8:
        return {"estado": "revision_manual", "candidato": auto}

    codigo = auto.get("theCode")
    if not codigo:
        return {"estado": "revision_manual", "candidato": auto}

    # 2. Verificación: el código existe y qué contiene
    info = client.get(f"{base}/codeinfo/{codigo}")

    return {
        "estado": "verificado",
        "codigo": codigo,
        "titulo": auto.get("matchingText"),
        "puntuacion": auto.get("matchScore"),
        "definicion": info.get("definition"),
    }


if __name__ == "__main__":
    client = IcdApiClient(
        os.environ["ICD_CLIENT_ID"], os.environ["ICD_CLIENT_SECRET"], language="es"
    )
    print(diagnostic_to_code(client, "neumonía adquirida en la comunidad"))
```

---

<a id="parametros"></a>

## 7. Referencia de parámetros

### 7.1 Parámetros de búsqueda en ICD-11 MMS

Endpoint: `/icd/release/11/{releaseId}/{linearizationname}/search`

| Parámetro | Endpoint | Tipo | Predeterminado | Descripción |
| --- | --- | --- | --- | --- |
| `q` | `/icd/release/11/{releaseId}/{linearizationname}/search` | string | — | Texto buscado. Un `%` al final de una palabra actúa de comodín para ella. |
| `medicalCodingMode` | `/icd/release/11/{releaseId}/{linearizationname}/search` | boolean | `true` | Modo de codificación médica: solo devuelve entidades con código y busca en todos los términos índice. Los capítulos 26, V y X quedan fuera. |
| `chapterFilter` | `/icd/release/11/{releaseId}/{linearizationname}/search` | string | — | Lista de capítulos separados por coma o punto y coma, por ejemplo `01;02;21`. |
| `subtreesFilter` | `/icd/release/11/{releaseId}/{linearizationname}/search` | string | — | Lista de URIs separadas por comas; la búsqueda se limita a esas entidades y sus descendientes. |
| `subtreeFilterUsesFoundationDescendants` | `/icd/release/11/{releaseId}/{linearizationname}/search` | boolean | `false` | Si es `true`, el filtro usa los descendientes del Fundamento en lugar de los de la linearización. |
| `useFlexisearch` | `/icd/release/11/{releaseId}/{linearizationname}/search` | boolean | `false` | Búsqueda laxa: los resultados no tienen que contener todas las palabras. |
| `flatResults` | `/icd/release/11/{releaseId}/{linearizationname}/search` | boolean | `true` | `true` devuelve una lista plana de coincidencias; `false`, una estructura anidada con la jerarquía. |
| `highlightingEnabled` | `/icd/release/11/{releaseId}/{linearizationname}/search` | boolean | `true` | Si es `false`, los resultados no incluyen las etiquetas de resaltado. |
| `includeKeywordResult` | `/icd/release/11/{releaseId}/{linearizationname}/search` | boolean | `false` | Añade la lista de palabras: completado de palabra si la última es incompleta, o sugerencias si es completa. |
| `propertiesToBeSearched` | `/icd/release/11/{releaseId}/{linearizationname}/search` | string | — | Solo se usa con `medicalCodingMode=false`. Valores válidos: `Title`, `FullySpecifiedName`, `Definition`, `Exclusion`, `IndexTerm`. |

> **Discrepancia documentada.** Para `flatResults`, la especificación OpenAPI declara
> `default: true` mientras que el texto de la OMS dice «Default value false». **Pasa el parámetro
> explícitamente** siempre que su valor importe; no dependas del valor por defecto.

### 7.2 Parámetros de búsqueda en el Fundamento

Endpoint: `/icd/entity/search`

| Parámetro | Endpoint | Tipo | Predeterminado | Descripción |
| --- | --- | --- | --- | --- |
| `q` | `/icd/entity/search` | string | — | Texto buscado. Admite el comodín `%` al final de una palabra. |
| `propertiesToBeSearched` | `/icd/entity/search` | string | — | Valores válidos: `Title`, `Synonym`, `NarrowerTerm`, `FullySpecifiedName`, `Definition`, `Exclusion`. Varios separados por comas. |
| `subtreesFilter` | `/icd/entity/search` | string | — | URIs separadas por comas que acotan el ámbito de la búsqueda. |
| `chapterFilter` | `/icd/entity/search` | string | — | Capítulos separados por coma o punto y coma. |
| `useFlexisearch` | `/icd/entity/search` | boolean | `false` | Búsqueda laxa. |
| `flatResults` | `/icd/entity/search` | boolean | `true` | Lista plana frente a estructura anidada. |
| `highlightingEnabled` | `/icd/entity/search` | boolean | `true` | Activa o desactiva el resaltado. |
| `releaseId` | `/icd/entity/search` | string | última | Fija la versión del Fundamento. Si se omite, se usa la última versión publicada. |

> Ojo: el conjunto de valores válidos de `propertiesToBeSearched` **difiere** entre el Fundamento
> (que admite `Synonym` y `NarrowerTerm`) y la linearización (que admite `IndexTerm` pero exige
> `medicalCodingMode=false`). No son intercambiables.

### 7.3 Parámetros de descripción de códigos

| Parámetro | Endpoint | Tipo | Predeterminado | Descripción |
| --- | --- | --- | --- | --- |
| `code` | `/icd/release/11/{releaseId}/{linearizationname}/describe` | string | — | Código o combinación de códigos a describir. `&` y `/` van codificados en la URL. |
| `uri` | `/icd/release/11/{releaseId}/{linearizationname}/describe` | string | — | URI del Fundamento o de la linearización, o combinación de ellas. |
| `simplify` | `/icd/release/11/{releaseId}/{linearizationname}/describe` | boolean | `false` | Simplifica la combinación postcoordinada si existe una entidad precoordinada equivalente. |
| `flexiblemode` | `/icd/release/11/{releaseId}/{linearizationname}/describe` | boolean | `false` | Tolera valores postcoordinados fuera de los conjuntos predefinidos. |
| `convertToTerminalCodes` | `/icd/release/11/{releaseId}/{linearizationname}/describe` | boolean | `false` | Sustituye los códigos por sus terminales (hojas). No afecta a las URI del Fundamento. |
| `flexiblemode` | `/icd/release/11/{releaseId}/{linearizationname}/codeinfo/{code}` | boolean | `false` | Tolera valores postcoordinados fuera de los conjuntos predefinidos. |
| `convertToTerminalCodes` | `/icd/release/11/{releaseId}/{linearizationname}/codeinfo/{code}` | boolean | `false` | Sustituye los códigos por sus terminales (hojas). |

### 7.4 Parámetros de autocodificación, localización y ficha

| Parámetro | Endpoint | Tipo | Predeterminado | Descripción |
| --- | --- | --- | --- | --- |
| `searchText` | `/icd/release/11/{releaseId}/{linearizationname}/autocode` | string | — | Texto diagnóstico de entrada. |
| `searchText` | `/icd/entity/autocode` | string | — | Texto diagnóstico de entrada (búsqueda en el Fundamento). |
| `matchThreshold` | `/icd/release/11/{releaseId}/{linearizationname}/autocode` | number | según la API | Puntuación mínima (entre 0 y 1) para incluir un resultado. |
| `matchThreshold` | `/icd/entity/autocode` | number | según la API | Puntuación mínima (entre 0 y 1) para incluir un resultado. |
| `subtreesFilter` | `/icd/release/11/{releaseId}/{linearizationname}/autocode` | string | — | URIs que acotan la búsqueda. En la MMS, los capítulos 26, V y X quedan fuera por defecto. |
| `subtreesFilter` | `/icd/entity/autocode` | string | — | URIs que acotan la búsqueda. |
| `foundationUri` | `/icd/release/11/{releaseId}/{linearizationname}/lookup` | string | — | URI de la entidad del Fundamento que se quiere localizar en la linearización. |
| `include` | `/icd/release/11/{releaseId}/{linearizationname}/{id}` | string | — | Propiedades adicionales: `ancestor`, `descendant`, `diagnosticCriteria`, separadas por comas. |
| `include` | `/icd/entity/{id}` | string | — | Propiedades adicionales: `ancestor`, `descendant`, `diagnosticCriteria`, separadas por comas. |
| `releaseId` | `/icd/entity` | string | última | Fija la versión del Fundamento. |
| `releaseId` | `/icd/entity/{id}` | string | última | Fija la versión del Fundamento. |
| `releaseId` | `/icd/entity/autocode` | string | última | Fija la versión del Fundamento. |

### 7.5 Parámetros de DORIS y CODEDIT

Ambos endpoints comparten el mismo conjunto de parámetros de certificado de defunción. Los campos de
causa aceptan **códigos** (`causeOfDeathCodeA`…`causeOfDeathCodeE`) o **URIs**
(`causeOfDeathUriA`…`causeOfDeathUriE`): basta con proporcionar una de las dos formas.

| Parámetro | Endpoint | Tipo | Descripción |
| --- | --- | --- | --- |
| `sex` | `/icd/release/11/{releaseId}/doris` | integer | `1` varón, `2` mujer, `9` desconocido. |
| `estimatedAge` | `/icd/release/11/{releaseId}/doris` | string | Duración ISO 8601, por ejemplo `P10YD` (10 años), `P9M` (9 meses), `P5D` (5 días). |
| `dateBirth` | `/icd/release/11/{releaseId}/doris` | string | Fecha de nacimiento en formato fecha y hora del W3C. |
| `dateDeath` | `/icd/release/11/{releaseId}/doris` | string | Fecha de defunción en formato fecha y hora del W3C. |
| `causeOfDeathCodeA` | `/icd/release/11/{releaseId}/doris` | string | Causa del campo A. Códigos separados por comas; admite combinaciones postcoordinadas. |
| `causeOfDeathCodeB` | `/icd/release/11/{releaseId}/doris` | string | Causa del campo B. |
| `causeOfDeathCodeC` | `/icd/release/11/{releaseId}/doris` | string | Causa del campo C. |
| `causeOfDeathCodeD` | `/icd/release/11/{releaseId}/doris` | string | Causa del campo D. |
| `causeOfDeathCodeE` | `/icd/release/11/{releaseId}/doris` | string | Causa del campo E. |
| `causeOfDeathUriA` | `/icd/release/11/{releaseId}/doris` | string | Causa del campo A expresada como URI. |
| `causeOfDeathUriB` | `/icd/release/11/{releaseId}/doris` | string | Causa del campo B expresada como URI. |
| `causeOfDeathUriC` | `/icd/release/11/{releaseId}/doris` | string | Causa del campo C expresada como URI. |
| `causeOfDeathUriD` | `/icd/release/11/{releaseId}/doris` | string | Causa del campo D expresada como URI. |
| `causeOfDeathUriE` | `/icd/release/11/{releaseId}/doris` | string | Causa del campo E expresada como URI. |
| `causeOfDeathCodePart2` | `/icd/release/11/{releaseId}/doris` | string | Causa de la parte 2 del certificado. |
| `causeOfDeathUriPart2` | `/icd/release/11/{releaseId}/doris` | string | Causa de la parte 2 expresada como URI. |
| `intervalA` | `/icd/release/11/{releaseId}/doris` | string | Intervalo entre inicio y defunción del campo A, en ISO 8601. |
| `intervalB` | `/icd/release/11/{releaseId}/doris` | string | Intervalo entre inicio y defunción del campo B, en ISO 8601. |
| `intervalC` | `/icd/release/11/{releaseId}/doris` | string | Intervalo entre inicio y defunción del campo C, en ISO 8601. |
| `intervalD` | `/icd/release/11/{releaseId}/doris` | string | Intervalo entre inicio y defunción del campo D, en ISO 8601. |
| `intervalE` | `/icd/release/11/{releaseId}/doris` | string | Intervalo entre inicio y defunción del campo E, en ISO 8601. |
| `surgeryWasPerformed` | `/icd/release/11/{releaseId}/doris` | integer | `0` no, `1` sí, `9` desconocido. |
| `surgeryDate` | `/icd/release/11/{releaseId}/doris` | string | Fecha de la cirugía, en formato W3C. |
| `surgeryReason` | `/icd/release/11/{releaseId}/doris` | string | Motivo de la cirugía. |
| `autopsyWasRequested` | `/icd/release/11/{releaseId}/doris` | integer | `0` no, `1` sí, `9` desconocido. |
| `autopsyFindings` | `/icd/release/11/{releaseId}/doris` | integer | `0` no, `1` sí, `9` desconocido. |
| `mannerOfDeath` | `/icd/release/11/{releaseId}/doris` | integer | Circunstancia de la defunción. |

> El conjunto completo de parámetros (incluidos los de muerte fetal, perinatal y materna) está en
> la especificación OpenAPI y es idéntico para `codedit` y `doris`.

---

<a id="respuesta"></a>

## 8. Formato de respuesta

### 8.1 JSON-LD y textos traducibles

La API usa JSON-LD. Los textos que dependen del idioma se devuelven como objetos
`LanguageSpecificText` con **dos claves: `@language` y `@value`**.

```json
{
  "@id": "http://id.who.int/icd/release/11/2025-01/mms/1466586723",
  "code": "1A00",
  "title": {
    "@language": "es",
    "@value": "Cólera"
  },
  "definition": {
    "@language": "es",
    "@value": "La cólera es una enfermedad infecciosa intestinal aguda..."
  },
  "classKind": "category",
  "source": "http://id.who.int/icd/entity/257068234"
}
```

> **No busques `title.value` ni `title.language`.** Las claves correctas son `@value` y `@language`.
> Es la diferencia entre parsear bien la respuesta y no parsearla nunca.

### 8.2 Entidades del Fundamento y de la linearización

| Esquema | Cuándo lo recibes | Campos característicos |
| --- | --- | --- |
| `FoundationEntity` | `/icd/entity/{id}` | `title`, `definition`, `longDefinition`, `fullySpecifiedName`, `synonym`, `inclusion`, `exclusion`, `narrowerTerm`, `child`, `parent`, `ancestor`, `descendant`, `browserUrl`. **Sin `code`.** |
| `LinearizationEntity` | `/icd/release/11/{releaseId}/{linearizationname}/{id}` | Todo lo anterior **más** `code`, `source`, `classKind`, `blockId`, `codeRange`, `codingNote`, `foundationChildElsewhere`, `indexTerm`, `postcoordinationScale`. |
| `TopLevelFoundation` | `/icd/entity` | `releaseId`, `releaseDate`, `availableLanguages`, `allReleases`, `supportedLinearizations`, `child`. |
| `TopLevelLinearization` | `/icd/release/11/{releaseId}/{linearizationname}` | `releaseId`, `releaseDate`, `availableLanguages`, `prereleaseLanguages`, `child` (capítulos). |

`classKind` admite estos valores: `chapter` (capítulo), `block` (agrupación superior sin código),
`window` (como `block` pero sin hijos en la linearización) y `category` (entidad con código).

### 8.3 Resultados de búsqueda

La búsqueda devuelve un `ISearchResult`. El campo con las coincidencias se llama
**`destinationEntities`** (no `entities`), y cada elemento es un `ISimpleEntity`:

| Campo | Descripción |
| --- | --- |
| `id` | URI de la entidad. |
| `title` | Título, con la parte coincidente marcada. |
| `code` | Código (solo en linearizaciones). |
| `isLeaf` | `true` si la entidad no tiene hijos. |
| `postcoordinationAvailability` | Si admite postcoordinación. |
| `hasCodingNote` | Si lleva nota de codificación. |
| `matchingPVs` | Propiedades que han coincidido con la búsqueda. |
| `chapter` | Capítulo al que pertenece. |
| `inclusion` / `exclusion` | Términos de inclusión y exclusión. |
| `isResidualOther` / `isResidualUnspecified` | Si es una residual «otra» o «no especificada». |

A nivel de resultado: `uniqueSearchId`, `guessType`, `resultChopped` (la búsqueda teve demasiados
resultados y se truncó), `wordSuggestionsChopped`, `words` (las sugerencias de palabra) y `error` /
`errorMessage`.

### 8.4 Autocodificación

`AutoCodingSearchResult` incluye: `searchText`, `matchingText` (la mejor frase encontrada),
`theCode`, `foundationURI`, `linearizationURI`, `matchScore` (0 a 1), `matchLevel` y `matchType`
(la propiedad donde se encontró la coincidencia).

### 8.5 Propiedades del esquema ICD

Las propiedades del Fundamento y de las linearizaciones proceden de dos vocabularios: el **esquema
ICD** de la OMS (`http://id.who.int/icd/schema/...`) y **SKOS** del W3C
(`http://www.w3.org/2004/02/skos/core#...`).

| Propiedad | Vocabulario | Significado |
| --- | --- | --- |
| `title` | SKOS `prefLabel` | Título de la entidad. |
| `definition` | SKOS `definition` | Caracterización breve: lo que siempre es cierto sobre la entidad. |
| `longDefinition` | ICD `longDefinition` | Información adicional: contexto, agentes etiológicos, circunstancias. |
| `fullySpecifiedName` | ICD `fullySpecifiedName` | Título inequívoco que no presupone contexto. |
| `synonym` | SKOS `altLabel` | Sinónimos. |
| `inclusion` | ICD `inclusion` | Términos de inclusión: ejemplos de diagnósticos que se clasifican aquí. |
| `exclusion` | ICD `exclusion` | Términos de exclusión: se clasifican en otro sitio. |
| `narrowerTerm` | ICD `narrowerTerm` | Términos más estrechos que no son sinónimos. |
| `parent` | SKOS `broaderTransitive` | URI de las entidades padre. |
| `child` | SKOS `narrowerTransitive` | URI de las entidades hijas. |
| `code` | ICD `code` | Código de la categoría. |
| `source` | ICD `source` | URI de la entidad del Fundamento de la que procede. |
| `classKind` | ICD `classKind` | `chapter`, `block`, `window` o `category`. |
| `browserUrl` | ICD `browserUrl` | Enlace directo a la entidad en el ICD-11 Browser de la OMS. |
| `postcoordinationScale` | ICD `postcoordinationScale` | Ejes de postcoordinación, si los hay, con sus conjuntos de valores. |
| `indexTerm` | ICD `indexTerm` | Todos los términos índice de la entidad, incluidos los de entidades del Fundamento no presentes en la linearización. |

### 8.6 El resaltado viene como HTML dentro del JSON

Cuando `highlightingEnabled` está activo (por defecto), el título llega con la parte coincidente
marcada con etiquetas HTML:

```json
{
  "title": "Vibrio <em class=\"found\">colera</em>"
}
```

**Trátalo como HTML no confiable.** Antes de insertarlo en tu interfaz, pásalo por un saneador
(sanitizador de HTML) o escápalo y aplica tú el resaltado. Si lo inyectas tal cual con
`innerHTML`, estás creando un vector de inyección de contenido.

---

<a id="errores"></a>

## 9. Errores y códigos de estado

| Código | Significado | Qué hacer |
| --- | --- | --- |
| `400` | Petición incorrecta (código o URI mal formados, combinación de códigos inválida). | Corrige los parámetros. Revisa en especial la codificación de `&` y `/`. |
| `401` | Falta el token, o el token ha caducado. | Pide un token nuevo y repite **una** vez. |
| `403` | El token es válido pero no tiene permisos suficientes. | Revisa el ámbito `icdapi_access` y las credenciales usadas. |
| `404` | El recurso no existe (entidad, versión o URI incorrectos). | Comprueba el `releaseId` y la URI. |
| `405` | Método no permitido en esa ruta. | Usa `GET`, o `POST` donde el endpoint lo soporte. |
| `406` | No se puede satisfacer la combinación de cabeceras `Accept` / `Accept-Language`. | Pide `application/json` y un idioma disponible en esa versión. |
| `415` | Tipo de medio no soportado. | Usa `application/json`. |
| `500` | Error del servidor. | Reintenta con espera creciente y, si persiste, comunícalo. |

El mensaje de error de la API llega como texto plano. Un ejemplo real de token ausente:

```text
Authentication failed. The request must include a valid and non-expired bearer token in the Authorization header.
```

Un patrón robusto de reintento ante `401`:

```bash
#!/usr/bin/env bash
# Reintenta una vez si el token ha caducado.
set -euo pipefail

TOKEN="${TOKEN:-}"
URL="https://id.who.int/icd/release/11/2025-01/mms/search?q=colera"

if [ -z "$TOKEN" ]; then
  TOKEN=$(curl -sS -X POST https://icdaccessmanagement.who.int/connect/token \
    -u "$ICD_CLIENT_ID:$ICD_CLIENT_SECRET" \
    -d grant_type=client_credentials \
    -d scope=icdapi_access \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
fi

status=$(curl -sS -o /tmp/opencode/icd-response.json -w "%{http_code}" -G "$URL" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/json" \
  -H "Accept-Language: es" \
  -H "API-Version: v2")

if [ "$status" = "401" ]; then
  TOKEN=$(curl -sS -X POST https://icdaccessmanagement.who.int/connect/token \
    -u "$ICD_CLIENT_ID:$ICD_CLIENT_SECRET" \
    -d grant_type=client_credentials \
    -d scope=icdapi_access \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
  curl -sS -G "$URL" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Accept: application/json" \
    -H "Accept-Language: es" \
    -H "API-Version: v2"
fi
```

---

<a id="practicas"></a>

## 10. Buenas prácticas

1. **Fija la versión.** No confíes en «la última versión»: la clasificación cambia entre
   releases y con ello cambian los códigos. Guarda el `releaseId` junto a cada dato que
   almacenes, y a la vista del usuario.
2. **Guarda el idioma junto a la URI.** La versión española y la inglesa de una misma categoría
   tienen URIs distintas. Persiste siempre la pareja (URI, idioma).
3. **Cachéa el token y las respuestas.** El token dura una hora; las respuestas de la clasificación
   cambian solo con los releases. Una caché con clave
   `(endpoint, parámetros, releaseId, idioma)` elimina la mayor parte del tráfico.
4. **Usa `POST` para búsquedas largas.** `GET` tiene un límite de 2 KB.
5. **Codifica `&` y `/` en los códigos.** `GC08&XN62R` se envía como `GC08%26XN62R`.
6. **Pasa los booleanos de forma explícita.** `medicalCodingMode`, `flatResults` y
   `highlightingEnabled` tienen valores por defecto que la documentación describe de forma
   inconsistente. Escríbelos siempre.
7. **Establece umbrales de confianza en la autocodificación.** `matchScore` va de 0 a 1; por debajo
   de tu umbral, manda a revisión humana.
8. **Sanea el resaltado.** Viene como HTML incrustado en el JSON (§8.6).
9. **Reintenta con espera creciente ante `500`**, y reintenta una sola vez ante `401` renovando el
   token.
10. **Respeta la clasificación, no solo la API.** La ICD-11 es una clasificación viva: sus
    entidades cambian entre versiones. Revisa las notas de versión antes de una migración:
    `https://icd.who.int/docs/icd-api/ReleaseNotes/`.
11. **Registra la versión de la API** (`API-Version: v2`) en tus logs de peticiones: ayuda a
    diagnosticar cambios de comportamiento tras una actualización.
12. **Para despliegues internos, considera una instancia local** (§11): sin límites de red y con
    control total sobre los datos que salen de tu organización.

---

<a id="despliegue-local"></a>

## 11. Despliegue local

La ICD API también se puede instalar en tu propia infraestructura, lo que resulta útil cuando hay
requisitos de aislamiento de datos, se necesitan performances predecibles o se quiere evitar
depender de la red pública.

| Opción | Documentación |
| --- | --- |
| Información general | `https://icd.who.int/docs/icd-api/ICDAPI-LocalDeployment/` |
| Contenedor Docker (con soporte ARM) | `https://icd.who.int/docs/icd-api/ICDAPI-DockerContainer/` |
| Servicio de Windows | `https://icd.who.int/docs/icd-api/ICDAPI-WindowsService/` |
| Servicio systemd en Linux | `https://icd.who.int/docs/icd-api/ICDAPI-SystemdService/` |

En una instancia local la URL base cambia y la autenticación se sustituye por una clave
administrativa; los endpoints, los parámetros y el formato de respuesta son los mismos.

---

<a id="recursos"></a>

## 12. Recursos

### Documentación oficial

| Recurso | Enlace |
| --- | --- |
| Portal de la ICD API (registro y claves) | `https://icd.who.int/icdapi` |
| Documentación de la API, versión 2.x | `https://icd.who.int/docs/icd-api/APIDoc-Version2/` |
| Referencia de la API (OpenAPI / Swagger) | `https://id.who.int/swagger/index.html` |
| Especificación OpenAPI descargable | `https://id.who.int/swagger/v2/swagger.json` |
| Autenticación | `https://icd.who.int/docs/icd-api/API-Authentication/` |
| Versiones e idiomas soportados | `https://icd.who.int/docs/icd-api/SupportedClassifications/` |
| Esquema ICD y propiedades | `https://icd.who.int/docs/icd-api/ICD-Schema/` |
| Soporte de DORIS y CODEDIT | `https://icd.who.int/docs/icd-api/DORISSupport/` |
| Soporte FHIR (prerelease) | `https://icd.who.int/docs/icd-api/ICDAPI-FHIR-Support/` |
| Notas de versión | `https://icd.who.int/docs/icd-api/ReleaseNotes/` |
| ICD-11 Browser | `https://icd.who.int/browse11` |
| Guía de referencia del ICD-11 | `https://icd.who.int/icd11refguide/es/index.html` |

### Código de ejemplo

- Repositorio oficial de muestras (C#, Java, JavaScript, Python, PHP…):
  `https://github.com/icd-api`

### Herramientas incrustadas

Las *Embedded Classification Tools* (ECT) son el ICD-11 Browser y la herramienta de codificación
como componentes incrustables en tu aplicación, alimentados por la misma API:
`https://icd.who.int/docs/icd-api/icd11ect-1.8/`.

---

<a id="apendices"></a>

## 13. Apéndices

### 13.1 Glosario ICD (español ↔ inglés)

| Español | Inglés | Significado |
| --- | --- | --- |
| Título | Title | Nombre corto de la entidad. |
| Nombre completamente especificado | Fully Specified Name | Título inequívoco que no depende del contexto jerárquico. |
| Sinónimo | Synonym | Nombre alternativo de la misma entidad. |
| Término de inclusión | Inclusion | Diagnóstico de ejemplo que se clasifica en esa categoría. |
| Término de exclusión | Exclusion | Diagnóstico que se clasifica en otra categoría. |
| Término más estrecho | Narrower term | Término más específico que no es sinónimo. |
| Definición | Definition | Caracterización breve de la entidad. |
| Información adicional | Long definition | Contexto y características adicionales. |
| Capítulo | Chapter | Nivel superior de la linearización. |
| Bloque | Block | Agrupación superior sin código. |
| Ventana | Window | Agrupación sin hijos en la linearización. |
| Categoría | Category | Entidad que tiene código. |
| Residual | Residual | Categoría de agregación: «otra» u «no especificada». |
| Tallo | Stem | Código base de una combinación postcoordinada. |
| Postcoordinación | Postcoordination | Combinación de un código base con códigos de extensión. |
| Eje de postcoordinación | Axis | Dimensión de extensión permitida o requerida. |
| Precoordinado | Precoordinated | Código único ya previsto en la clasificación. |
| Entidad de la Fundación | Foundation entity | Entidad del Fundamento, sin código. |
| Linearización | Linearization | Lista tabular derivada del Fundamento. |
| Nota de codificación | Coding note | Guía de uso durante la codificación. |
| Término índice | Index term | Términos de búsqueda generados para la entidad. |
| Deprecado | Deprecated | Término obsoleto que ya no se muestra en los navegadores. |
| Causa subyacente de muerte | Underlying cause of death | Causa que determinan las reglas de la ICD (DORIS). |

### 13.2 Glosario de la API

| Término | Significado |
| --- | --- |
| `releaseId` | Identificador de versión, con formato `AAAA-MM` (por ejemplo `2025-01`). |
| `linearizationname` | Nombre corto de la linearización: `mms` o `icf`. |
| `residual` | `other` u `unspecified`. |
| `include` | Lista de propiedades opcionales a incluir en la respuesta. |
| `stemCode` | Código base de una combinación postcoordinada. |
| `simplifiedCode` | Código tras simplificar una combinación postcoordinada. |
| `otherPostcoordination` | Valores postcoordinados que no encajan en ningún eje conocido. |
| `classKind` | Tipo de entidad: `chapter`, `block`, `window` o `category`. |
| `availableLanguages` | Idiomas disponibles para la clasificación o el Fundamento. |
| `prereleaseLanguages` | Idiomas cuya traducción aún no es estable. |
| `foundationChildElsewhere` | Hijos del Fundamento que no están en esta linearización (los «hijos grises»). |

### 13.3 Comprobación rápida de la instalación

Si tu integración funciona, estas cuatro comprobaciones deberían cumplirse:

1. `GET /icd/release/11/2025-01/mms` responde `200` y su `availableLanguages` contiene `es`.
2. `GET /icd/release/11/2025-01/mms/search?q=colera` con `Accept-Language: es` devuelve títulos con
   `@language` igual a `es`.
3. `GET /icd/release/11/2025-01/mms/describe?code=1A00` devuelve una entidad con `code` `1A00`.
4. `GET /icd/release/11/2025-01/mms/lookup?foundationUri=...` devuelve la entidad equivalente en la
   MMS.

Si alguna falla, revisa en este orden: token vigente → `API-Version: v2` → `Accept: application/json`
→ `Accept-Language: es` → `releaseId` válido.

---

*Documento elaborado a partir de la especificación OpenAPI 3.0.1 publicada por la OMS en
`https://id.who.int/swagger/v2/swagger.json` y de la documentación oficial del ICD-API. La copia de
la especificación usada para verificar este documento está en `icd-api-swagger.json` junto a él, y
la comprobación automática se ejecuta con `python3 verify_doc.py`.*
