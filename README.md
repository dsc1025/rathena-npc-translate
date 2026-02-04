# Translate simplified GBK

## **[rathena github](https://github.com/rathena/rathena)**

## Usage

**Scripts**

- **script/batch_convert_to_gbk.py**: Batch-convert `*.zh-cn.txt` UTF-8 files to GBK Examples:
```bash
python -m script.batch_convert_to_gbk npc/re/guides/
python -m script.batch_convert_to_gbk npc/re/ --recursive
python -m script.batch_convert_to_gbk npc/re/guides/ --force
```
See [script/batch_convert_to_gbk.py](script/batch_convert_to_gbk.py)

- **script/batch_translate.py**: Scan a directory for `.txt` files and write missing `.zh-cn.txt` translation outputs (skips existing outputs unless `--force`). Examples:
```bash
python -m script.batch_translate npc/custom/
python -m script.batch_translate npc/custom/ --recursive --force
```
See [script/batch_translate.py](script/batch_translate.py)

- **script/switch_npc_path.py**: Scan a `.conf` for `npc:` references and report missing `.zh-cn.txt` counterparts. Use `--suffix` to update the `.conf` in-place (replace `.txt` -> `.zh-cn.txt`) when the counterpart exists. Examples:
```bash
python -m script.switch_npc_path script/some.conf
python -m script.switch_npc_path npc/re/scripts_athena.conf --suffix
```
See [script/switch_npc_path.py](script/switch_npc_path.py)

Notes: Run commands from the project root so imports and `npc/` paths resolve correctly; prefer the `-m package.module` form when running scripts that rely on package-relative imports.



## Other Setting

### Create char chinese name
conf/inter_athena.conf
```
// You can specify the codepage to use in your MySQL tables here.
// (Note that this feature requires MySQL 4.1+)
default_codepage: GBK
```

### Disable Pincode
conf/char_athena.conf
```
//===================================
// Pincode system
//===================================
// NOTE: Requires client 2011-03-09aragexeRE or newer.
// A window is opened before you can select your character and you will have to enter a pincode by using only your mouse.
// Default: yes
pincode_enabled: no

```