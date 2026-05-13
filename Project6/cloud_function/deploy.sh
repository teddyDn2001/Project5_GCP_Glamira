#!/usr/bin/env bash
#
# Deploy / redeploy the Project 06 Cloud Function (Gen 2) with an Eventarc
# GCS finalize trigger. Idempotent — the same command is used for create and
# update.
#
# Required env vars (load from ../.env or export manually before running):
#   GCP_PROJECT_ID, GCP_REGION
#   BQ_DATASET_RAW, BQ_LOCATION
#   CF_NAME, CF_RUNTIME, CF_ENTRY_POINT
#   CF_SERVICE_ACCOUNT
#   CF_TRIGGER_BUCKET
#
# Usage:
#   ../scripts && set -a && source ../.env && set +a && bash deploy.sh
#
set -euo pipefail

: "${GCP_PROJECT_ID:?Missing GCP_PROJECT_ID}"
: "${GCP_REGION:?Missing GCP_REGION}"
: "${BQ_DATASET_RAW:?Missing BQ_DATASET_RAW}"
: "${BQ_LOCATION:?Missing BQ_LOCATION}"
: "${CF_NAME:?Missing CF_NAME}"
: "${CF_RUNTIME:?Missing CF_RUNTIME}"
: "${CF_ENTRY_POINT:?Missing CF_ENTRY_POINT}"
: "${CF_SERVICE_ACCOUNT:?Missing CF_SERVICE_ACCOUNT}"
: "${CF_TRIGGER_BUCKET:?Missing CF_TRIGGER_BUCKET}"

# Always run from the cloud_function/ directory so --source=. picks up the right files.
cd "$(dirname "$0")"

echo "[deploy] project=${GCP_PROJECT_ID} region=${GCP_REGION} fn=${CF_NAME}"
echo "[deploy] trigger bucket=${CF_TRIGGER_BUCKET}"
echo "[deploy] runtime=${CF_RUNTIME} entry-point=${CF_ENTRY_POINT}"
echo "[deploy] service account=${CF_SERVICE_ACCOUNT}"

# NOTE on permissions:
#   * The deploying user needs roles/cloudfunctions.developer + roles/iam.serviceAccountUser
#     on ${CF_SERVICE_ACCOUNT} (so they can attach it to the function).
#   * The Eventarc service agent needs roles/eventarc.eventReceiver and
#     roles/run.invoker — gcloud usually grants these automatically the first
#     time you deploy a Gen 2 function with an Eventarc trigger.

gcloud functions deploy "${CF_NAME}" \
  --gen2 \
  --project="${GCP_PROJECT_ID}" \
  --region="${GCP_REGION}" \
  --runtime="${CF_RUNTIME}" \
  --source=. \
  --entry-point="${CF_ENTRY_POINT}" \
  --trigger-event-filters="type=google.cloud.storage.object.v1.finalized" \
  --trigger-event-filters="bucket=${CF_TRIGGER_BUCKET}" \
  --service-account="${CF_SERVICE_ACCOUNT}" \
  --memory=512Mi \
  --cpu=1 \
  --timeout=540s \
  --max-instances=5 \
  --retry \
  --set-env-vars="GCP_PROJECT_ID=${GCP_PROJECT_ID},BQ_DATASET_RAW=${BQ_DATASET_RAW},BQ_LOCATION=${BQ_LOCATION}"

echo
echo "[deploy] tail logs with:"
echo "  gcloud functions logs read ${CF_NAME} --gen2 --region=${GCP_REGION} --limit=50"
