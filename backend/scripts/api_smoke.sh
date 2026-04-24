#!/usr/bin/env bash
# End-to-end smoke test of the garage-ai REST API against the local emulator.
# Wipes Firestore first, then runs every endpoint in dependency order.
# Each test prints   PASS/FAIL  METHOD  PATH  →  expected
set -u

API=http://127.0.0.1:8000/api/v1
KEY="dev-secret-key"
PROJECT="garage-ai-test"
EMU="localhost:8080"

pass=0
fail=0
failures=()

# --- helpers --------------------------------------------------------------

_req() { # _req METHOD PATH [json-body] → prints body; exports HTTP_STATUS
  local method=$1 path=$2 body=${3:-}
  local resp
  if [ -n "$body" ]; then
    resp=$(curl -sS -o /tmp/resp.body -w "%{http_code}" -X "$method" "$API$path" \
      -H "X-API-Key: $KEY" -H "Content-Type: application/json" -d "$body")
  else
    resp=$(curl -sS -o /tmp/resp.body -w "%{http_code}" -X "$method" "$API$path" \
      -H "X-API-Key: $KEY")
  fi
  HTTP_STATUS=$resp
  cat /tmp/resp.body
}

check() { # check "LABEL" EXPECTED_STATUS [jq-filter-must-be-true]
  local label=$1 want=$2 jq_filter=${3:-}
  local ok=1 reason=""
  if [ "$HTTP_STATUS" != "$want" ]; then
    ok=0; reason="status $HTTP_STATUS, want $want"
  elif [ -n "$jq_filter" ]; then
    if ! jq -e "$jq_filter" /tmp/resp.body >/dev/null 2>&1; then
      ok=0; reason="jq filter failed: $jq_filter"
    fi
  fi
  if [ $ok -eq 1 ]; then
    printf "  \033[32mPASS\033[0m  %s\n" "$label"
    pass=$((pass+1))
  else
    printf "  \033[31mFAIL\033[0m  %s  (%s)\n" "$label" "$reason"
    printf "        body: %s\n" "$(head -c 300 /tmp/resp.body)"
    failures+=("$label")
    fail=$((fail+1))
  fi
}

# --- 0. reset emulator ----------------------------------------------------

echo "== Wipe Firestore emulator =="
curl -sS -X DELETE "http://$EMU/emulator/v1/projects/$PROJECT/databases/(default)/documents" >/dev/null
echo "  cleared"

# --- 1. health ------------------------------------------------------------

echo; echo "== health =="
_req GET "/health" >/dev/null
check "GET /health" 200 '.status == "ok"'

# --- 2. suppliers ---------------------------------------------------------

echo; echo "== suppliers =="
_req POST "/suppliers" '{"name":"Nhà cung cấp A","phone":"0901234567","address":"HN"}' >/dev/null
SUPPLIER_ID=$(jq -r '.id' /tmp/resp.body)
check "POST /suppliers (create)" 201 '.id and .name == "Nhà cung cấp A"'

_req GET "/suppliers" >/dev/null
check "GET /suppliers (list)" 200 'type == "array" and length >= 1'

_req GET "/suppliers/$SUPPLIER_ID" >/dev/null
check "GET /suppliers/{id}" 200 '.id != null'

_req PATCH "/suppliers/$SUPPLIER_ID" '{"phone":"0912345678"}' >/dev/null
check "PATCH /suppliers/{id}" 200 '.phone == "0912345678"'

# --- 3. customers ---------------------------------------------------------

echo; echo "== customers =="
_req POST "/customers" '{"name":"Anh Nam","phone":"0987654321"}' >/dev/null
CUSTOMER_ID=$(jq -r '.id' /tmp/resp.body)
check "POST /customers (create)" 201 '.id and .name == "Anh Nam"'

_req GET "/customers" >/dev/null
check "GET /customers (list)" 200 'type == "array" and length >= 1'

_req GET "/customers/$CUSTOMER_ID" >/dev/null
check "GET /customers/{id}" 200 '.id != null'

_req PATCH "/customers/$CUSTOMER_ID" '{"phone":"0900000001"}' >/dev/null
check "PATCH /customers/{id}" 200 '.phone == "0900000001"'

_req GET "/customers/$CUSTOMER_ID/history" >/dev/null
check "GET /customers/{id}/history (empty)" 200 'type == "array"'

# --- 4. products (two — auto-SKU and explicit SKU) -----------------------

echo; echo "== products =="
_req POST "/products" '{"name":"Dầu nhớt 5W-30","selling_price":200000}' >/dev/null
P1_SKU=$(jq -r '.sku' /tmp/resp.body)
check "POST /products (auto-SKU from VN name)" 201 '.sku == "DAUNHOT5W30"'

_req POST "/products" '{"name":"Lọc gió","sku":"AIRFILTER","selling_price":120000}' >/dev/null
P2_SKU=$(jq -r '.sku' /tmp/resp.body)
check "POST /products (explicit SKU)" 201 '.sku == "AIRFILTER"'

_req GET "/products" >/dev/null
check "GET /products (list)" 200 'type == "array" and length == 2'

_req GET "/products/$P1_SKU" >/dev/null
check "GET /products/{sku}" 200 '.sku != null'

_req PATCH "/products/$P1_SKU" '{"selling_price":210000}' >/dev/null
check "PATCH /products/{sku}" 200 '.selling_price == 210000'

# --- 5. invoices: import (stock purchase) --------------------------------

echo; echo "== invoices: import =="
IMPORT_BODY=$(jq -n --arg sid "$SUPPLIER_ID" --arg s1 "$P1_SKU" --arg s2 "$P2_SKU" '{
  type:"import",
  supplier_id:$sid,
  items:[
    {sku:$s1, quantity:10, unit_price:150000},
    {sku:$s2, quantity:20, unit_price:80000}
  ],
  notes:"Nhập đầu kho"
}')
_req POST "/invoices" "$IMPORT_BODY" >/dev/null
IMPORT_ID=$(jq -r '.id' /tmp/resp.body)
check "POST /invoices (import)" 201 '.id and .type == "import" and .total_cost == 3100000'

# Verify stock updated and last_import_price captured
_req GET "/products/$P1_SKU" >/dev/null
check "POST /invoices import → stock incremented on P1" 200 '.quantity == 10 and .average_cost == 150000'
_req GET "/products/$P2_SKU" >/dev/null
check "POST /invoices import → stock incremented on P2" 200 '.quantity == 20 and .average_cost == 80000'

# --- 6. invoices: service (sale / repair) --------------------------------

echo; echo "== invoices: service =="
SVC_BODY=$(jq -n --arg cid "$CUSTOMER_ID" --arg s1 "$P1_SKU" '{
  type:"service",
  customer_id:$cid,
  items:[
    {sku:$s1, quantity:2, unit_price:210000},
    {description:"Công thay dầu", quantity:1, unit_price:50000}
  ],
  notes:"Thay dầu + lọc"
}')
_req POST "/invoices" "$SVC_BODY" >/dev/null
SVC_ID=$(jq -r '.id' /tmp/resp.body)
check "POST /invoices (service, mixed product+labor)" 201 '.id and .type == "service" and .total_revenue == 470000'

_req GET "/products/$P1_SKU" >/dev/null
check "POST /invoices service → stock decremented on P1" 200 '.quantity == 8'

# --- 7. invoices: list + get --------------------------------------------

echo; echo "== invoices: read =="
_req GET "/invoices" >/dev/null
check "GET /invoices (list)" 200 'type == "array" and length == 2'

_req GET "/invoices/$SVC_ID" >/dev/null
check "GET /invoices/{id}" 200 '(.id != null) and ((.items | length) >= 1)'

# --- 8. invoice adjustment ----------------------------------------------

echo; echo "== invoices: adjustment =="
ADJ_BODY=$(jq -n '{type:"amend", reason:"khách trả thiếu 20k"}')
_req POST "/invoices/$SVC_ID/adjustments" "$ADJ_BODY" >/dev/null
check "POST /invoices/{id}/adjustments" 201 '.id != null'

# After adjustment, the invoice should transition to status=adjusted
_req GET "/invoices/$SVC_ID" >/dev/null
check "GET /invoices/{id} shows status=adjusted after adjustment" 200 '.status == "adjusted" and (.adjustments | length == 1)'

# --- 9. reports ----------------------------------------------------------

echo; echo "== reports =="
_req GET "/reports/daily" >/dev/null
check "GET /reports/daily (service-only counts)" 200 '.invoice_count == 1 and .total_revenue == 470000 and .profit == 170000'

YEAR=$(date +%Y)
MONTH=$(date +%-m)
_req GET "/reports/monthly?year=$YEAR&month=$MONTH" >/dev/null
check "GET /reports/monthly" 200 '.invoice_count == 1 and .total_revenue == 470000'

_req GET "/reports/top-products" >/dev/null
check "GET /reports/top-products" 200 'type == "array"'

TODAY=$(date +%Y-%m-%d)
_req GET "/reports/revenue-summary?from=$TODAY&to=$TODAY" >/dev/null
check "GET /reports/revenue-summary" 200 'type == "object"'

# --- 10. customer history (now populated) -------------------------------

echo; echo "== customer history =="
_req GET "/customers/$CUSTOMER_ID/history" >/dev/null
check "GET /customers/{id}/history (after invoice)" 200 'type == "array" and length >= 1'

# --- 11. deletes (leave suppliers/customers clean) ----------------------

echo; echo "== deletes =="
_req DELETE "/customers/$CUSTOMER_ID" >/dev/null
check "DELETE /customers/{id}" 204 ''

_req DELETE "/suppliers/$SUPPLIER_ID" >/dev/null
check "DELETE /suppliers/{id}" 204 ''

# --- 12. auth boundary --------------------------------------------------

echo; echo "== auth boundary =="
resp=$(curl -sS -o /tmp/resp.body -w "%{http_code}" "$API/products")
HTTP_STATUS=$resp
check "GET /products without key → 401" 401 '.'

resp=$(curl -sS -o /tmp/resp.body -w "%{http_code}" "$API/products" -H "X-API-Key: wrong-key")
HTTP_STATUS=$resp
check "GET /products wrong key → 401" 401 '.'

# --- summary -----------------------------------------------------------

echo
if [ $fail -eq 0 ]; then
  printf "\033[32m== ALL PASSED: %d/%d ==\033[0m\n" "$pass" "$((pass+fail))"
  exit 0
else
  printf "\033[31m== FAILED: %d, PASSED: %d ==\033[0m\n" "$fail" "$pass"
  for f in "${failures[@]}"; do printf "  · %s\n" "$f"; done
  exit 1
fi
