# M27 Security Model

## Fail closed

* Unknown connectors denied  
* Mode OFF / DRAINING / DISABLED denied  
* Domain not allowlisted denied  
* Forbidden payload/header keys denied  
* Non-allowlisted local commands denied  
* Trading connectors cannot register  
* Cloud live operations blocked by policy  

## Secrets

* Never stored in code  
* Auth uses env var **names** or local secure dir presence  
* Authorization / cookie / api_key headers stripped from HTTP adapter  
* Evidence and events run through redaction  

## Network

* Remote HTTP requires HTTPS (loopback may use HTTP)  
* Link-local / metadata hosts globally denied  
* Redirects not followed by default transport  

## Process

* Local tools: `shell=False`, fixed argv only  
* No arbitrary subprocess binary paths  

## Invariants preserved

```text
cloud fallback = disabled
Trading Guardian = UNCHANGED / UNENGAGED
connector bypass = false on all framework results
production_certified computed (not forced)
```
