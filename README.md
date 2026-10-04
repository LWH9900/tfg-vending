# Vimach

Vimach es una aplicación web desarrollada como parte de un Trabajo de Fin de Grado del Grado en Ingeniería Informática – Ingeniería del Software de la Escuela Técnica Superior de Ingeniería Informática (ETSII) de la Universidad de Sevilla. Vimach reúne en una única aplicación la gestión de las máquinas expendedoras y de las operaciones relacionadas con ellas. Permite controlar el inventario, registrar compras, reposiciones y ventas, organizar los productos dentro de cada máquina y gestionar los precios. También incluye una proyección de ventas para ayudar a prever futuras necesidades de compra y reposición.

## Instalación y ejecución

### Requisitos previos

Para ejecutar la aplicación es necesario tener instalado:

- Git.
- Docker Desktop, iniciado y en ejecución.

La aplicación se ha probado en Windows con Git 2.46.2.windows.1 y Docker Desktop 4.43.2 (199162). Es posible que funcione correctamente con otras versiones, aunque no se han verificado de forma específica.

### 1. Clonar el repositorio

```bash
git clone <URL_DEL_REPOSITORIO>
cd tfg-vending
```

### 2. Crear el archivo `.env`

El repositorio incluye un archivo `.env.example` con las variables necesarias. Debe copiarse con el nombre `.env` antes de levantar los contenedores.

El archivo `.env` debe contener una configuración similar a la siguiente:

```env
POSTGRES_DB=vending_db
POSTGRES_USER=vending_user
POSTGRES_PASSWORD=change-me
POSTGRES_HOST=db
POSTGRES_PORT=5432

DJANGO_SECRET_KEY=change-me
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
```

Las variables que puede ser necesario modificar son:

- `POSTGRES_PASSWORD`: contraseña del usuario de PostgreSQL. Para una ejecución local puede establecerse una contraseña propia.
- `DJANGO_SECRET_KEY`: clave utilizada internamente por Django. Debe sustituirse por un valor propio.
- `DJANGO_ALLOWED_HOSTS`: hosts desde los que se permitirá acceder a la aplicación. Solo es necesario modificarla si se va a acceder desde una dirección distinta de las configuradas por defecto.

### 3. Levantar la aplicación

Con Docker Desktop en ejecución, desde la raíz del proyecto:

```bash
docker compose up -d --build
```
La opción `-d` (`--detach`) ejecuta los contenedores en segundo plano.

En las ejecuciones posteriores puede utilizarse simplemente:

```bash
docker compose up -d
```

Al iniciar el servicio web se ejecutan automáticamente las migraciones de Django antes de arrancar el servidor.

### 4. Cargar datos de demostración (opcional)

La aplicación puede utilizarse con una base de datos vacía o poblarse con datos de prueba mediante el comando:

```bash
docker compose exec web python manage.py seed_demo_data
```

### 5. Acceder a la aplicación

Con los contenedores en ejecución, la aplicación estará disponible en http://localhost:8000

## Gestión de la base de datos

### Vaciar los datos

Para eliminar los datos almacenados por Django manteniendo la estructura de la base de datos:

```bash
docker compose exec web python manage.py flush
```

Django solicitará confirmación antes de eliminar los datos.

## Ejecución de pruebas y comprobaciones
Los siguientes pasos se incluyen únicamente para reproducir las pruebas y comprobaciones descritas en la memoria del Trabajo de Fin de Grado. No son necesarios para poner en marcha y utilizar la aplicación.

### 1. Instalar las dependencias de desarrollo

Las herramientas utilizadas para las pruebas y comprobaciones adicionales se encuentran en `requirements-dev.txt`. Con los contenedores en ejecución:

```bash
docker compose exec web pip install -r requirements-dev.txt
```

### 2. Ejecutar la suite de pruebas

Las pruebas basadas en propiedades están etiquetadas con `hypothesis`. Estas pruebas ejecutan un gran número de casos generados automáticamente y, por tanto, pueden aumentar el tiempo total de ejecución de la suite. Si únicamente se desea ejecutar las pruebas funcionales y automatizadas convencionales, pueden excluirse mediante:

```bash
docker compose exec web python manage.py test --exclude-tag=hypothesis
```
Para reutilizar la base de datos de pruebas entre ejecuciones:
```bash
docker compose exec web python manage.py test --exclude-tag=hypothesis --keepdb --noinput
```

### 3. Ejecutar la suite completa de pruebas

Para ejecutar todas las pruebas, incluidas las realizadas con Hypothesis:

```bash
docker compose exec web coverage run manage.py test
```
Para mostrar posteriormente el informe de cobertura:

```bash
docker compose exec web coverage report -m
```

### Nota sobre los tiempos de las pruebas con Hypothesis

Las pruebas con Hypothesis tienen configurado un límite de tiempo (`deadline`). Aunque se ha establecido con margen respecto a los tiempos observados durante el desarrollo, en equipos más lentos puede producirse algún `DeadlineExceeded` o `FlakyFailure` debido al tiempo de ejecución. En ese caso, puede ser necesario aumentar el `deadline` configurado.

## Herramientas adicionales de validación

Durante el desarrollo también se utilizaron herramientas adicionales para validar distintos aspectos de la aplicación. 

### Mutation testing con Cosmic Ray

El informe obtenido durante la validación del proyecto se incluye en el fichero `cosmic-ray-report.txt`.

Si se desea repetir la prueba, pueden utilizarse los siguientes comandos:

Inicializar la sesión de mutation testing:
```bash
docker compose exec web cosmic-ray init cosmic-ray-all.toml cosmic-ray-all.sqlite
```

Ejecutar la línea base para comprobar que la suite funciona correctamente antes de generar mutantes:

```bash
docker compose exec web cosmic-ray baseline cosmic-ray-all.toml
```

Ejecutar los mutantes:

```bash
docker compose exec web cosmic-ray exec cosmic-ray-all.toml cosmic-ray-all.sqlite
```

Consultar el resultado de la ejecución:

```bash
docker compose exec web cr-report cosmic-ray-all.sqlite
```

### Pruebas de carga con Locust

Con la aplicación en ejecución, Locust puede iniciarse mediante:

```bash
docker compose exec web locust \
  -f locustfile.py \
  --host=http://localhost:8000 \
  --web-host=0.0.0.0 \
  --web-port=8089 \
  --class-picker
```

La interfaz web de Locust está disponible en http://localhost:8089

