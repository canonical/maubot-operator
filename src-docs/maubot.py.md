<!-- markdownlint-disable -->

<a href="../src/maubot.py#L0"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

# <kbd>module</kbd> `maubot.py`
Maubot service. 

**Global Variables**
---------------
- **MAUBOT_ROOT_URL**

---

<a href="../src/maubot.py#L33"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>function</kbd> `login`

```python
login(admin_name: str, admin_password: str) → str
```

Login in Maubot and returns a token. 



**Args:**
 
 - <b>`admin_name`</b>:  admin name that will do the login. 
 - <b>`admin_password`</b>:  admin password. 



**Raises:**
 
 - <b>`APIError`</b>:  error while interacting with Maubot API. 



**Returns:**
 token to be used in further requests. 


---

<a href="../src/maubot.py#L60"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>function</kbd> `register_account`

```python
register_account(
    token: str,
    account_name: str,
    account_password: str,
    matrix_server: str
) → str
```

Register account. 



**Args:**
 
 - <b>`token`</b>:  valid token for authentication. 
 - <b>`account_name`</b>:  account name to be registered. 
 - <b>`account_password`</b>:  account password to be registered. 
 - <b>`matrix_server`</b>:  Matrix server where the account will be registered. 



**Raises:**
 
 - <b>`APIError`</b>:  error while interacting with Maubot API. 



**Returns:**
 Account access information. 


---

## <kbd>class</kbd> `APIError`
Exception raised when something fails while interacting with Maubot API. 

Attrs:  msg (str): Explanation of the error. 

<a href="../src/maubot.py#L24"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>function</kbd> `__init__`

```python
__init__(msg: str)
```

Initialize a new instance of the MaubotError exception. 



**Args:**
 
 - <b>`msg`</b> (str):  Explanation of the error. 





