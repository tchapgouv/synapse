## To run

1. Execute [Tchap Docker Integration](https://github.com/tchapgouv/tchap-docker-integration)
- COMPOSE_PROFILES should have `with_local_synapse`
2. Install Synapse Dependencies:
```
pip install pipx
pipx install poetry
poetry install --extras all
```
3. In `build_conf.sh`, set the path of the Tchap Docker Integration repo in `$DOCKER_DEMO_REPO`
4. Execute the build of the homeserver configuration file
```
./build_conf.sh
```
5. Execute Synapse 
```
poetry run python -m synapse.app.homeserver -c homeserver.yaml
```

NOTE : this version use Sqlite database