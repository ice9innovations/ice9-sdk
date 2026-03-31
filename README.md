# ice9 SDKs

Monorepo for the `ice9` SDKs.

## Packages

- `python/` - Python SDK published to PyPI as `ice9`
- `nodejs/` - Node.js SDK published to npm as `@ice9/sdk`

## Package Development

Python:

```bash
cd python
python -m pytest
python -m build
```

Node.js:

```bash
cd nodejs
npm install
npm test
npm run build
```

## Consumer Installation

Python users install from PyPI:

```bash
pip install ice9
```

Node.js users install from npm:

```bash
npm install @ice9/sdk
```
