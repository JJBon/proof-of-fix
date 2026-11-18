# The watcher's Lambda image (proof-of-fix#152, platform#219): validator-kit/lambda/watcher.py on AWS's Lambda Python
# base image, pinned by digest (the multi-platform index of public.ecr.aws/lambda/python:3.12; the seats host's Lambda is
# arm64). boto3 comes with the base image; the watcher needs nothing else.
# Build from the repository root: scripts/seats-image.sh watcher <repository url> (or --build-only watcher).
# The validator kit still deploys the same file as a zip (validator-kit/terraform/watcher.tf): its behaviour is unchanged.
FROM public.ecr.aws/lambda/python:3.12@sha256:dd6af79e07defe9988a761cd126ee9ba038d6ed6cf0e7c4e3350eac91892a554

COPY validator-kit/lambda/watcher.py ${LAMBDA_TASK_ROOT}/watcher.py
CMD ["watcher.handler"]
