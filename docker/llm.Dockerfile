# syntax=docker/dockerfile:1
# The LLM server (A1, D22): llama.cpp's official server image with the model
# baked in, so the pod needs no network at all and the image can be carried
# into an isolated site.
#
#   docker build -f docker/llm.Dockerfile \
#     --build-arg MODEL_FILE=gemma-4-E2B_q4_0-it.gguf dist/models
#
# The build context is only the models directory. There is no RUN step, so
# the image builds for any architecture without emulation.

ARG LLAMA_SERVER_IMAGE=ghcr.io/ggml-org/llama.cpp:server-v0.5.0

FROM ${LLAMA_SERVER_IMAGE}
ARG MODEL_FILE
ARG MODEL_SOURCE
LABEL socialsignal.model.file="${MODEL_FILE}" \
      socialsignal.model.source="${MODEL_SOURCE}"
# No --chmod: BuildKit would apply it to the /models directory it creates
# too, and a directory without the execute bit cannot be entered (found by
# testing). The file keeps its 0644 mode and is owned by root, so the
# server's user can read it but not change it.
COPY ${MODEL_FILE} /models/model.gguf

# What defines this artefact is fixed here: which model, under which name
# (the worker stores it with each label), and that it never touches the
# network or serves the web UI. Tuning (threads, context, reasoning) comes
# from the Helm chart as arguments.
ENTRYPOINT ["/app/llama-server", "--model", "/models/model.gguf", \
            "--alias", "gemma-4-E2B-it-qat-q4_0", \
            "--offline", "--no-webui", "--host", "0.0.0.0", "--port", "8080"]

# The upstream image runs as root; ours never does. Numeric, so Kubernetes
# can verify runAsNonRoot.
USER 10001:10001
