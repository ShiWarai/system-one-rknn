#!/bin/sh
# Меняет плейсхолдер service-template на slug нового репозитория.
# Запускать один раз после «Use this template».
set -eu

if [ "$#" -ne 1 ]; then
  echo "usage: $0 <slug>" >&2
  echo "slug: строчные латинские буквы, цифры и дефисы, например my-service" >&2
  exit 1
fi

slug="$1"
case "$slug" in
  ""|*[!a-z0-9-]*|-*|*-|*--*|service-template)
    echo "недопустимый slug: ${slug}" >&2
    exit 1
    ;;
esac

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)

files="
README.md
AGENTS.md
docs/cicd.md
.env.example
docker-compose.yml
docker-compose.dev.yml
docker-compose.prerelease.yml
docker-compose.prod.yml
.github/workflows/deploy.yml
.github/workflows/publish.yml
"

for rel in $files; do
  if [ ! -f "${root}/${rel}" ]; then
    echo "нет файла: ${rel}" >&2
    exit 1
  fi
  sed -i "s/service-template/${slug}/g" "${root}/${rel}"
done

echo "готово: service-template → ${slug}"
