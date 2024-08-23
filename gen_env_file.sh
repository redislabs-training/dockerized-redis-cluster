#!/bin/bash


IMAGE_NAME="redis"
FILE_NAME="env-orig"


BASE_URL="https://registry.hub.docker.com/v2/repositories/library/$IMAGE_NAME/tags"
TAGS=()
fetch_tags() {
    local url=$1
    response=$(curl -s "$url")
    tags=$(echo $response | jq -r '.results[].name')
    TAGS+=($tags)
    next=$(echo $response | jq -r '.next')
    if [ "$next" != "null" ]; then
        fetch_tags "$next"
    fi
}
fetch_tags "$BASE_URL"
echo "REDIS_VER=latest" > $FILE_NAME
for TAG in "${TAGS[@]}"; do
  if [ "$TAG" != "latest" ]; then
    echo "#REDIS_VER=$TAG" >> $FILE_NAME
  fi
done

echo " $FILE_NAME file has been generated."
