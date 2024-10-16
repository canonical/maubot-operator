<!-- markdownlint-disable -->

<a href="../src/charm.py#L0"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

# <kbd>module</kbd> `charm.py`
Maubot charm service. 

**Global Variables**
---------------
- **BLACKBOX_NAME**
- **MAUBOT_CONFIGURATION_PATH**
- **MAUBOT_NAME**
- **NGINX_NAME**


---

## <kbd>class</kbd> `EventFailError`
Exception raised when an event fails. 





---

## <kbd>class</kbd> `MaubotCharm`
Maubot charm. 

<a href="../src/charm.py#L61"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>function</kbd> `__init__`

```python
__init__(*args: Any)
```

Construct. 



**Args:**
 
 - <b>`args`</b>:  Arguments passed to the CharmBase parent constructor. 


---

#### <kbd>property</kbd> app

Application that this unit is part of. 

---

#### <kbd>property</kbd> charm_dir

Root directory of the charm as it is running. 

---

#### <kbd>property</kbd> config

A mapping containing the charm's config and current values. 

---

#### <kbd>property</kbd> meta

Metadata of this charm. 

---

#### <kbd>property</kbd> model

Shortcut for more simple access the model. 

---

#### <kbd>property</kbd> unit

Unit that this execution is responsible for. 




---

## <kbd>class</kbd> `MissingRelationDataError`
Custom exception to be raised in case of malformed/missing relation data. 

<a href="../src/charm.py#L43"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>function</kbd> `__init__`

```python
__init__(message: str, relation_name: str) → None
```

Init custom exception. 



**Args:**
 
 - <b>`message`</b>:  Exception message. 
 - <b>`relation_name`</b>:  Relation name that raised the exception. 





