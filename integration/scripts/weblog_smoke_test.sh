#!/usr/bin/env bash
#
# weblog_smoke_test.sh
#
# Quick smoke test of weblog ingress for a deployed DUM service. The script:
#
#   1. Creates a few empty (valid, zero-content) gzip files named like weblogs.
#   2. Uploads them with pds-ingress-client using --weblogs.
#   3. Confirms each file arrived in the weblogs bucket at the expected key with
#      the expected size.
#   4. Deletes exactly those objects from the bucket and confirms they are gone.
#
# Every file name contains a unique run ID, and only the exact keys created by
# this run are ever deleted. Nothing is deleted by prefix.
#
# Requirements:
#   - pds-ingress-client on the PATH (or set PDS_INGRESS_CLIENT to its location)
#   - AWS CLI with credentials allowed to s3:GetObject and s3:DeleteObject on the
#     weblogs bucket (the DUM client itself authenticates via the INI config)
#
# Note: on a bucket with versioning enabled, the delete leaves a delete marker
# and the uploaded (empty) object versions are retained.
#
# Exit status is 0 only if the upload, verification, delete and delete
# verification all succeed.

set -u -o pipefail

NODE="eng"
LOG_TYPE="smoketest"
NUM_FILES=3
CONFIG=""
BUCKET=""
REGION=""
PROFILE=""
CLIENT="${PDS_INGRESS_CLIENT:-pds-ingress-client}"

usage() {
    cat <<EOF
Usage: $(basename "$0") --bucket BUCKET --config CONFIG --region REGION --profile PROFILE [options]

Required:
  --bucket BUCKET      Name of the weblogs S3 bucket the files are expected to land in
  --config CONFIG      Path to the pds-ingress-client INI config file
  --region REGION      AWS region used for the aws CLI calls
  --profile PROFILE    AWS CLI profile used for the aws CLI calls

Options:
  --node NODE          PDS node ID to upload as (default: ${NODE})
  --log-type LOG_TYPE  Log type passed to --weblogs, lower case letters/digits (default: ${LOG_TYPE})
  --count COUNT        Number of files to create, 1-20 (default: ${NUM_FILES})
  --help               Show this help

Options accept either "--option value" or "--option=value".
EOF
}

fail_usage() {
    echo "ERROR: $1" >&2
    usage >&2
    exit 2
}

while [ $# -gt 0 ]; do
    case "$1" in
        --help)
            usage
            exit 0
            ;;
        --*=*)
            opt="${1%%=*}"
            val="${1#*=}"
            shift
            ;;
        --*)
            [ $# -ge 2 ] || fail_usage "Option $1 requires a value"
            case "$2" in
                --*) fail_usage "Option $1 requires a value, but got $2" ;;
            esac
            opt="$1"
            val="$2"
            shift 2
            ;;
        *) fail_usage "Unexpected argument: $1" ;;
    esac

    case "${opt}" in
        --bucket) BUCKET="${val}" ;;
        --config) CONFIG="${val}" ;;
        --region) REGION="${val}" ;;
        --profile) PROFILE="${val}" ;;
        --node) NODE="${val}" ;;
        --log-type) LOG_TYPE="${val}" ;;
        --count) NUM_FILES="${val}" ;;
        *) fail_usage "Unknown option: ${opt}" ;;
    esac
done

[ -n "${BUCKET}" ] || fail_usage "A weblogs bucket name is required (--bucket)"
[ -n "${CONFIG}" ] || fail_usage "A DUM client config file is required (--config)"
[ -n "${REGION}" ] || fail_usage "An AWS region is required (--region)"
[ -n "${PROFILE}" ] || fail_usage "An AWS CLI profile is required (--profile)"
[ -f "${CONFIG}" ] || fail_usage "Config file not found: ${CONFIG}"
[[ "${NODE}" =~ ^[a-z]+$ ]] || fail_usage "--node must be lower case letters only: ${NODE}"
[[ "${LOG_TYPE}" =~ ^[a-z0-9]+$ ]] || fail_usage "--log-type must be lower case letters/digits only: ${LOG_TYPE}"
[[ "${NUM_FILES}" =~ ^[0-9]+$ ]] && [ "${NUM_FILES}" -ge 1 ] && [ "${NUM_FILES}" -le 20 ] \
    || fail_usage "--count must be a number from 1 to 20: ${NUM_FILES}"

command -v aws >/dev/null 2>&1 || { echo "ERROR: aws CLI not found on PATH" >&2; exit 2; }
command -v "${CLIENT}" >/dev/null 2>&1 || { echo "ERROR: ${CLIENT} not found on PATH" >&2; exit 2; }

aws_cli() {
    aws --region "${REGION}" --profile "${PROFILE}" "$@"
}

# Prints the object size and returns 0 if the object exists, returns 1 if it
# does not exist, and prints the error and returns 2 for any other failure.
object_size() {
    local key="$1" output
    if output=$(aws_cli s3api head-object --bucket "${BUCKET}" --key "${key}" \
        --query ContentLength --output text 2>&1); then
        echo "${output}"
        return 0
    fi
    case "${output}" in
        *"404"* | *"Not Found"*) return 1 ;;
    esac
    echo "${output}"
    return 2
}

RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-$$"

# Resolve symlinks (for example /var -> /private/var on macOS) so the client
# sees the same path that is given as the --prefix
WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/dum-weblog-smoke.XXXXXX")" || exit 1
WORK_DIR="$(cd "${WORK_DIR}" && pwd -P)"
trap 'rm -rf "${WORK_DIR}"' EXIT

LOCAL_FILES=()
KEYS=()
SIZES=()
# Per-key result of the upload check: present, missing or unknown
STATES=()

for i in $(seq 1 "${NUM_FILES}"); do
    name="access_log.smoketest-${RUN_ID}-${i}.gz"
    # A gzip stream containing no data: a valid .gz file with empty content
    gzip -n -c </dev/null >"${WORK_DIR}/${name}"
    LOCAL_FILES+=("${WORK_DIR}/${name}")
    SIZES+=("$(wc -c <"${WORK_DIR}/${name}" | tr -d ' ')")
    # Object key layout used by the ingress service: <node>/<trimmed path>, where
    # the client replaces --prefix with weblogs/<node>-<log type>
    KEYS+=("${NODE}/weblogs/${NODE}-${LOG_TYPE}/${name}")
done

echo "== Weblog smoke test =="
echo "Node:      ${NODE}"
echo "Log type:  ${LOG_TYPE}"
echo "Bucket:    ${BUCKET}"
echo "Region:    ${REGION}"
echo "Profile:   ${PROFILE}"
echo "Run ID:    ${RUN_ID}"
echo "Files:     ${NUM_FILES}"
echo

STATUS=0

echo "== 1. Uploading with ${CLIENT} =="
"${CLIENT}" -c "${CONFIG}" -n "${NODE}" -w "${LOG_TYPE}" -p "${WORK_DIR}" \
    -r "${WORK_DIR}/report.json" "${LOCAL_FILES[@]}"
CLIENT_RC=$?

if [ "${CLIENT_RC}" -ne 0 ]; then
    echo "FAIL: ${CLIENT} exited with status ${CLIENT_RC}" >&2
    STATUS=1
fi

echo
echo "== 2. Verifying objects in s3://${BUCKET} =="
for idx in "${!KEYS[@]}"; do
    key="${KEYS[$idx]}"
    expected="${SIZES[$idx]}"
    if size=$(object_size "${key}"); then
        STATES+=("present")
        if [ "${size}" = "${expected}" ]; then
            echo "OK:   ${key} (${size} bytes)"
        else
            echo "FAIL: ${key} has ${size} bytes, expected ${expected}" >&2
            STATUS=1
        fi
    else
        rc=$?
        if [ "${rc}" -eq 1 ]; then
            STATES+=("missing")
            echo "FAIL: ${key} was not found" >&2
        else
            STATES+=("unknown")
            echo "FAIL: could not check ${key}: ${size}" >&2
        fi
        STATUS=1
    fi
done

echo
echo "== 3. Deleting the test objects =="
KEY_PATTERN="^${NODE}/weblogs/${NODE}-${LOG_TYPE}/access_log\.smoketest-[0-9TZ]+-[0-9]+-[0-9]+\.gz$"
for idx in "${!KEYS[@]}"; do
    key="${KEYS[$idx]}"
    # Delete only an object confirmed present by head-object
    if [ "${STATES[$idx]}" != "present" ]; then
        echo "Skipped (not confirmed in bucket): ${key}"
        continue
    fi
    # Only ever delete keys this run generated
    if ! [[ "${key}" =~ ${KEY_PATTERN} ]]; then
        echo "FAIL: refusing to delete unexpected key ${key}" >&2
        STATUS=1
        continue
    fi
    if aws_cli s3api delete-object --bucket "${BUCKET}" --key "${key}" >/dev/null; then
        echo "Deleted: ${key}"
    else
        echo "FAIL: could not delete ${key}" >&2
        STATUS=1
    fi
done

echo
echo "== 4. Confirming the test objects are gone =="
for key in "${KEYS[@]}"; do
    if size=$(object_size "${key}"); then
        echo "FAIL: ${key} still exists after delete" >&2
        STATUS=1
    else
        rc=$?
        if [ "${rc}" -eq 1 ]; then
            echo "OK:   ${key} is gone"
        else
            echo "FAIL: could not check ${key}: ${size}" >&2
            STATUS=1
        fi
    fi
done

echo
if [ "${STATUS}" -eq 0 ]; then
    echo "PASS: weblog upload to s3://${BUCKET} succeeded and test objects were removed"
else
    echo "FAIL: weblog smoke test did not pass" >&2
fi

exit "${STATUS}"
