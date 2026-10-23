"""Appairage, erreurs sous les champs, https impose, re-appairage."""

from __future__ import annotations

from homeassistant.config_entries import SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType

from custom_components.curiosa.const import (
    CONF_CODE,
    CONF_DEVELOPER,
    CONF_TOKEN,
    CONF_URL,
    DOMAIN,
)

from .fake_curiosa import EXPIRED_CODE, GOOD_CODE, LIMITED_CODE, TOKEN


async def start(hass):
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})


async def submit(hass, flow_id, url, code, developer=True):
    return await hass.config_entries.flow.async_configure(
        flow_id, {CONF_URL: url, CONF_CODE: code, CONF_DEVELOPER: developer}
    )


async def test_pairing_ok(hass, fake, entry_factory) -> None:
    result = await start(hass)
    assert result["type"] is FlowResultType.FORM
    result = await submit(hass, result["flow_id"], fake.url, "abcd-2345")
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_TOKEN] == TOKEN
    assert result["data"][CONF_URL] == fake.api_url
    assert result["data"][CONF_DEVELOPER] is True
    pair = next(r for r in fake.requests if r["path"].endswith("/pair"))
    assert pair["body"] == {"code": GOOD_CODE, "name": "Home Assistant"}
    assert "Authorization" not in pair["headers"]
    await hass.async_block_till_done()
    for entry in hass.config_entries.async_entries(DOMAIN):
        await hass.config_entries.async_unload(entry.entry_id)


async def test_wrong_code_error_under_field(hass, fake) -> None:
    result = await submit(hass, (await start(hass))["flow_id"], fake.url, "ZZZZ9999")
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_CODE: "invalid_code"}


async def test_expired_code(hass, fake) -> None:
    result = await submit(hass, (await start(hass))["flow_id"], fake.url, EXPIRED_CODE)
    assert result["errors"] == {CONF_CODE: "code_expired"}


async def test_too_many_tries(hass, fake) -> None:
    result = await submit(hass, (await start(hass))["flow_id"], fake.url, LIMITED_CODE)
    assert result["errors"] == {CONF_CODE: "too_many"}


async def test_bad_code_format_makes_no_request(hass, fake) -> None:
    result = await submit(hass, (await start(hass))["flow_id"], fake.url, "123")
    assert result["errors"] == {CONF_CODE: "invalid_code_format"}
    assert fake.requests == []


async def test_site_unreachable(hass, fake) -> None:
    url = fake.url
    await fake.stop()
    result = await submit(hass, (await start(hass))["flow_id"], url, GOOD_CODE)
    assert result["errors"] == {"base": "cannot_connect"}


async def test_module_missing_is_reported_on_address(hass, fake) -> None:
    result = await submit(hass, (await start(hass))["flow_id"], f"{fake.url}/m/autre/ha", GOOD_CODE)
    assert result["errors"] == {CONF_URL: "not_found"}


async def test_https_is_required(hass, fake) -> None:
    flow = await start(hass)
    result = await submit(hass, flow["flow_id"], "http://mon-site.com", GOOD_CODE, developer=False)
    assert result["errors"] == {CONF_URL: "https_required"}
    result = await submit(hass, flow["flow_id"], "http://mon-site.com", GOOD_CODE, developer=True)
    assert result["errors"] == {CONF_URL: "https_required"}
    assert fake.requests == []


async def test_local_address_needs_developer_mode(hass, fake) -> None:
    result = await submit(
        hass, (await start(hass))["flow_id"], fake.url, GOOD_CODE, developer=False
    )
    assert result["errors"] == {CONF_URL: "private_address"}
    assert fake.requests == []


async def test_already_configured(hass, fake, entry_factory) -> None:
    await entry_factory(fake)
    result = await submit(hass, (await start(hass))["flow_id"], fake.url, GOOD_CODE)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert [r for r in fake.requests if r["path"].endswith("/pair")] == []  # code non consomme


async def test_reauth_after_401(hass, fake, service_calls, entry_factory) -> None:
    entry = await entry_factory(fake, token="revoked-token")
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert len(flows) == 1
    result = await hass.config_entries.flow.async_configure(flows[0]["flow_id"], {CONF_CODE: "bad"})
    assert result["errors"] == {CONF_CODE: "invalid_code_format"}
    result = await hass.config_entries.flow.async_configure(
        flows[0]["flow_id"], {CONF_CODE: "ZZZZ9999"}
    )
    assert result["errors"] == {CONF_CODE: "invalid_code"}
    result = await hass.config_entries.flow.async_configure(
        flows[0]["flow_id"], {CONF_CODE: GOOD_CODE}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    await hass.async_block_till_done()
    assert entry.data[CONF_TOKEN] == TOKEN
    assert entry.state.name == "LOADED"
