
echo "Exporting environment variables from .env"
export $(grep -v '^#' .env | xargs)


