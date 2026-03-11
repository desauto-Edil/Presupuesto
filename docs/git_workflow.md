# Flujo de trabajo Git — IMPERANDINA

## Estructura de ramas

```
main          ← Producción estable. Solo merge desde release o hotfix.
develop       ← Rama de integración. Merge desde feature branches.
feature/*     ← Nuevas funcionalidades.
fix/*         ← Correcciones de bugs.
hotfix/*      ← Correcciones urgentes en producción.
release/*     ← Preparación de versiones.
```

### Flujo típico

```
feature/mi-funcionalidad  →  develop  →  release/v1.x  →  main
fix/nombre-del-bug        →  develop
hotfix/nombre-del-fix     →  main (y back-merge a develop)
```

## Convención de commits

Formato: `tipo(scope): descripción breve en español`

### Tipos válidos

| Tipo | Uso |
|---|---|
| `feat` | Nueva funcionalidad |
| `fix` | Corrección de bug |
| `refactor` | Refactorización sin cambio de comportamiento |
| `test` | Agregar o mejorar tests |
| `docs` | Documentación |
| `style` | Formato, espacios (sin lógica) |
| `chore` | Mantenimiento, deps, CI |
| `data` | Cambios en seeds o datos maestros |
| `config` | Cambios de configuración |

### Ejemplos

```bash
feat(despiece): agregar motor PowerGrip Plus TPO
fix(apu): corregir cálculo de días en mano de obra
test(services): agregar tests para DependenciaService
docs(readme): actualizar pasos de instalación
data(seed): agregar clientes demo para pruebas
config(settings): migrar a variables de entorno con python-decouple
chore(deps): actualizar Django a 4.2.29
```

## Primer push al repositorio remoto

```bash
# 1. Inicializar git (si aún no está hecho)
cd imperandina
git init

# 2. Agregar archivos (excluyendo los del .gitignore)
git add .
git status  # Verificar qué se incluirá

# 3. Commit inicial
git commit -m "chore: setup inicial del proyecto Imperandina"

# 4. Conectar con repositorio remoto (GitHub/GitLab)
git remote add origin https://github.com/ORGANIZACION/imperandina.git

# 5. Renombrar rama a main (si se llama master)
git branch -M main

# 6. Push
git push -u origin main

# 7. Crear rama develop
git checkout -b develop
git push -u origin develop
```

## Flujo de feature branch

```bash
# Crear rama desde develop
git checkout develop
git pull origin develop
git checkout -b feature/motor-apu

# Trabajar...
git add .
git commit -m "feat(apu): implementar APUService con materiales y mano de obra"

# Push y PR
git push origin feature/motor-apu
# Abrir Pull Request en GitHub: feature/motor-apu → develop
```

## Versiones y tags

```bash
# Crear tag de versión
git tag -a v1.0.0 -m "Release v1.0.0 - Primer entregable: motor PowerGrip"
git push origin v1.0.0

# Listar tags
git tag -l
```
