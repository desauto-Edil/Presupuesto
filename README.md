# IMPERANDINA — Sistema de Presupuestos Paramétricos

Sistema interno para la generación automática de despieces y APU (Análisis de Precio Unitario)
para proyectos de cubiertas y fachadas industriales.

---

## Tabla de contenidos

1. [Requisitos del sistema](#requisitos-del-sistema)
2. [Instalación local (macOS)](#instalación-local-macos)
3. [Configuración de base de datos](#configuración-de-base-de-datos)
4. [Estructura del proyecto](#estructura-del-proyecto)
5. [Comandos principales](#comandos-principales)
6. [Flujo de negocio](#flujo-de-negocio)
7. [API / Vistas principales](#api--vistas-principales)
8. [Motor PowerGrip](#motor-powergrip)
9. [Pruebas](#pruebas)
10. [Troubleshooting](#troubleshooting)

---

## Requisitos del sistema

| Componente | Versión mínima |
|---|---|
| Python | 3.9+ |
| Django | 4.2.x |
| PostgreSQL | 14+ |
| psycopg2-binary | 2.9+ |

---

## Instalación local (macOS)

### 1. Clonar el repositorio

```bash
git clone <URL_REPOSITORIO>
cd imperandina
```

### 2. Crear y activar entorno virtual

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 4. Configurar variables de entorno

```bash
cp .env.example .env
# Editar .env con tus credenciales locales
nano .env
```

### 5. Crear la base de datos PostgreSQL

```bash
psql -U postgres -f docs/setup_postgres.sql
```

O manualmente:

```sql
CREATE USER imperandina_user WITH PASSWORD 'tu_password_seguro';
CREATE DATABASE presupuestos OWNER imperandina_user;
GRANT ALL PRIVILEGES ON DATABASE presupuestos TO imperandina_user;
```

### 6. Aplicar migraciones

```bash
python manage.py migrate
```

### 7. Crear superusuario Django

```bash
python manage.py createsuperuser
```

### 8. Cargar datos maestros (seed)

```bash
# Datos PowerGrip base
python manage.py seed_powergrip

# Seed completo con datos de prueba (clientes, proveedores, proyectos demo)
python manage.py seed_full
```

### 9. Iniciar servidor de desarrollo

```bash
python manage.py runserver
```

Acceder a:
- **Admin:** http://127.0.0.1:8080/admin/
- **Proyectos:** http://127.0.0.1:8080/proyectos/
- **API Despiece:** http://127.0.0.1:8080/api/despiece/

---

## Configuración de base de datos

Ver archivo `.env.example` para la lista completa de variables de entorno requeridas.

Configuración mínima en `.env`:

```
DB_NAME=presupuestos
DB_USER=imperandina_user
DB_PASSWORD=tu_password
DB_HOST=localhost
DB_PORT=5432
```

### Backup y restauración

```bash
# Backup completo
pg_dump -U imperandina_user -h localhost presupuestos > backups/backup_$(date +%Y%m%d).sql

# Backup solo datos (sin DDL)
pg_dump -U imperandina_user -h localhost --data-only presupuestos > backups/data_$(date +%Y%m%d).sql

# Restaurar
psql -U imperandina_user -h localhost presupuestos < backups/backup_YYYYMMDD.sql
```

---

## Estructura del proyecto

```
imperandina/
├── manage.py                   # CLI Django
├── requirements.txt            # Dependencias Python
├── .env.example                # Plantilla de variables de entorno
├── .gitignore
├── README.md
│
├── docs/
│   ├── setup_postgres.sql      # Script SQL para crear BD y usuario
│   └── git_workflow.md         # Convenciones de ramas y commits
│
├── imperandina/                # Configuración Django
│   ├── settings.py             # Configuración principal (usa .env)
│   ├── urls.py                 # Rutas raíz
│   ├── wsgi.py
│   └── asgi.py
│
├── core/                       # Aplicación principal
│   ├── models.py               # 23 modelos de dominio
│   ├── services.py             # Motor de cálculo (Despiece, APU, Proyecto)
│   ├── views.py                # Vistas Django (HTML + JSON)
│   ├── forms.py                # Formularios ModelForm
│   ├── urls.py                 # Rutas de la app core
│   ├── admin.py                # Interfaz Django Admin
│   ├── apps.py
│   ├── tests.py                # Suite de pruebas unitarias
│   ├── migrations/
│   │   └── 0001_initial.py
│   └── templates/
│       └── core/
│           ├── base.html
│           ├── proyecto_list.html
│           ├── proyecto_detalle.html
│           ├── variables_form.html
│           ├── apu_form.html
│           └── apu_detalle.html
│
└── management/
    └── commands/
        ├── seed_powergrip.py   # Seed datos maestros PowerGrip
        └── seed_full.py        # Seed completo con datos demo
```

---

## Comandos principales

```bash
# Migraciones
python manage.py makemigrations
python manage.py migrate
python manage.py showmigrations

# Seeds
python manage.py seed_powergrip              # Solo datos PowerGrip
python manage.py seed_powergrip --reset      # Reset + recarga
python manage.py seed_full                   # Datos completos demo
python manage.py seed_full --reset           # Reset todo + recarga

# Pruebas
python manage.py test core                   # Todos los tests de core
python manage.py test core.tests.DespieceServiceTestCase   # Una clase
python manage.py test core --verbosity=2    # Con detalles

# Django shell
python manage.py shell

# Verificar configuración
python manage.py check
python manage.py diffsettings

# Servidor de desarrollo
python manage.py runserver
python manage.py runserver 0.0.0.0:8080     # Accesible en red local
```

---

## Flujo de negocio

```
Cliente → Solicitud → Proyecto → ProyectoSistema → Despiece → APU → Cotización
```

### Estados del proyecto

| Estado | Descripción |
|---|---|
| BORRADOR | Proyecto creado, sin datos completos |
| SOLICITUD | Proyecto asociado a una solicitud aprobada |
| DESPIECE | Despiece paramétrico ejecutado |
| DESPIECE_VALIDADO | Despiece revisado y aprobado |
| APU | APU en construcción |
| APU_GENERADO | APU completo y calculado |
| COTIZADO | Cotización formal enviada |
| APROBADO | Cotización aprobada por cliente |
| CERRADO | Proyecto finalizado |
| ANULADO | Proyecto cancelado |

---

## API / Vistas principales

| URL | Método | Descripción |
|---|---|---|
| `/proyectos/` | GET | Lista de proyectos |
| `/proyectos/<id>/` | GET | Detalle de proyecto |
| `/proyectos/<id>/variables/` | GET/POST | Variables dinámicas (total_powergip, cuadrilla) |
| `/proyectos/<id>/despiece/` | POST | Ejecutar despiece paramétrico |
| `/proyectos/<id>/apu/` | GET/POST | Formulario APU (costos de entrada) |
| `/proyectos/<id>/apu/detalle/` | GET | Resultado detallado del APU |
| `/api/proyectos/<id>/despiece/` | POST | API JSON: ejecutar despiece |
| `/api/proyectos/<id>/apu/` | POST | API JSON: generar APU |

---

## Motor PowerGrip

El sistema implementa dos variantes del algoritmo PowerGrip:

### Universal 7
| Producto | Fórmula |
|---|---|
| Fijaciones HDF | `(8 × Total_PowerGrip) × 1.01` |
| Limpiador | `((Total_PowerGrip × 0.04) / 50) × 1.01` |
| Estopa | `Limpiador / 2` |
| Sellador WaterBlock | `((Total_PowerGrip × 0.56) / 12) × 1.01` |

### Plus TPO
| Producto | Fórmula |
|---|---|
| Fijaciones HDF | `(9 × Total_PowerGrip) × 1.01` |
| Limpiador | `((Total_PowerGrip × 0.09) / 50) × 1.01` |
| Estopa | `Limpiador / 2` |
| Sellador Cut Edge | `((Total_PowerGrip × 1.16) / 36.1) × 1.01` |

---

## Pruebas

```bash
# Ejecutar toda la suite
python manage.py test core --verbosity=2

# Ejecutar una clase específica
python manage.py test core.tests.APUServiceTestCase

# Con cobertura (requiere coverage)
pip install coverage
coverage run manage.py test core
coverage report -m
coverage html  # Genera htmlcov/index.html
```

### Clases de prueba disponibles

| Clase | Qué prueba |
|---|---|
| `ConsecutivoTestCase` | Numeración automática SOL-YYYY-NNNN |
| `ReglaCalculoTestCase` | Evaluación de fórmulas Python |
| `PowerGripAlgoritmoTestCase` | Algoritmos hardcoded U7 y Plus TPO |
| `DespieceServiceTestCase` | Motor de despiece completo |
| `DependenciaServiceTestCase` | Inyección automática de dependencias |
| `APUServiceTestCase` | Generación de APU por categorías |
| `ProyectoServiceTestCase` | Flujo completo solicitud → APU |
| `SolicitudTestCase` | Gestión de solicitudes y contactos |
| `VariablesDinamicasTestCase` | Variables dinámicas en contexto |

---

## Troubleshooting

### Error: `could not connect to server`
Verificar que PostgreSQL esté corriendo:
```bash
brew services start postgresql@14
# O para PostgreSQL instalado diferente:
pg_ctl -D /usr/local/var/postgresql@14 start
```

### Error: `role "imperandina_user" does not exist`
Crear el usuario primero:
```bash
psql -U postgres -c "CREATE USER imperandina_user WITH PASSWORD 'tu_password';"
```

### Error: `django.db.utils.OperationalError`
Verificar credenciales en `.env` y que el archivo sea leído correctamente.

### Error en seed: `IntegrityError`
Ejecutar con `--reset`:
```bash
python manage.py seed_full --reset
```

### Tests fallan por BD
Los tests crean una base de datos temporal. Verificar que el usuario tenga permisos `CREATEDB`:
```sql
ALTER USER imperandina_user CREATEDB;
```
