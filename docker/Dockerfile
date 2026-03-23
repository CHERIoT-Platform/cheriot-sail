# Use a base image suited for your model (e.g., Ubuntu or Python)
FROM ubuntu:22.04

# Install system dependencies for Sail
RUN apt-get update && apt-get install -y git build-essential opam zlib1g-dev libgmp-dev

# Example: Installing the Sail ISA language/model
#RUN opam switch create 4.14.1 && \
#    opam exec -- opam install sail -y

# 4. Set the path so 'sail' is available when you log in later
#ENV PATH="/root/.opam/4.14.1/bin:${PATH}"

# Set the working directory inside the container
WORKDIR /home
