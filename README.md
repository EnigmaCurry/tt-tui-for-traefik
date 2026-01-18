# rust-cli-template

This is my Rust template for new CLI apps.

## Features

 * [Just](https://github.com/casey/just) enabled project build
   targets.
 * [Clap](https://docs.rs/clap/latest/clap/) CLI argument parser.
 * Bash / Fish / Zsh shell (tab)
   [completion](https://docs.rs/clap_complete/latest/clap_complete/).
 * GitHub actions for tests and releases:
   * Builds executables for multiple platforms.
   * Builds Docker images for x86_64 and aarch64.
   * Test coverage report published to GitHub pages.
   * Publishing crates to crates.io (disabled by default, uncomment in
   [release.yml](template/.github/workflows/release.yml)).

## Use this template

 * [Create a new repository using this template](https://github.com/new?template_name=rust-cli-template&template_owner=EnigmaCurry).
 * The `Repository name` that you choose will also be used as your new app's name.
 * If you have enabled code coverage reports (it's on by default), go
   to the GitHub repository `Settings` page:
   * Find `Pages`.
   * Find `Build and deployment`.
   * Find `Source` and set it to `GitHub Actions`. (**Not** `Deploy
     from a branch`)

## Clone your new repository to your to your workstation.

```
## For example:

git clone git@github.com:${USERNAME}/${REPOSITORY}.git \
   ~/git/vendor/${USERNAME}/${REPOSITORY}

cd ~/git/vendor/${USERNAME}/${REPOSITORY}
```

## Render the template

After cloning the repository to your workstation, you must initialize
 it:

```
./setup.sh
```

This will render the template files into the project root and then
self-destruct this README.md and the template.

It will also build and run the initial tests. Importantly, this will
also create the Cargo.lock file for the first time.

## Run the program

```
just run [ARGS ...]
```

You can also run the binary directly by building manually (`just
build`) and running the static binary
`{{app_name}}/target/debug/{{app_name}}`.

## Commit the initial app source files

Once you've verified that the tests ran correctly, you can add all of
the files the template generated, as well as the `Cargo.lock` file,
into the git repository. Commit and push your changes:

```
## For example:

git add .
git commit -m "init"
git push
```

You're now ready to start developing your application.

## Releasing your app

See [DEVELOPMENT.md](template/DEVELOPMENT.md) for instructions on the
release process, a copy of this file has been included in your new git
repository's root.
 
