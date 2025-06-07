# -*- coding: utf-8 -*-
import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List
import pytest
import copy

from app.crud.json_repository import JsonStorageRepository, COMMON_ID_FIELDS

# Define a common entity type for testing
TEST_ENTITY_TYPE = "widgets"
TEST_ENTITY_ID_FIELD = "widget_id" # Using a custom ID field not in COMMON_ID_FIELDS initially
ALTERNATIVE_ID_FIELD = "name" # Another potential ID field

# Add TEST_ENTITY_ID_FIELD to COMMON_ID_FIELDS for some tests to ensure indexing works
EXTENDED_COMMON_ID_FIELDS = COMMON_ID_FIELDS + [TEST_ENTITY_ID_FIELD, ALTERNATIVE_ID_FIELD]

@pytest.fixture
def temp_data_dir(tmp_path: Path) -> Path:
    data_dir = tmp_path / "test_data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir

@pytest.fixture
def file_paths_config(temp_data_dir: Path) -> Dict[str, Path]:
    # Using relative paths from base_data_dir for the config
    return {
        TEST_ENTITY_TYPE: Path(f"{TEST_ENTITY_TYPE}_db.json"),
        "gadgets": Path("gadgets_data/gadgets_store.json") # Test with subdirectory
    }

@pytest.fixture
def json_repository(temp_data_dir: Path, file_paths_config: Dict[str, Path]) -> JsonStorageRepository:
    # Temporarily extend COMMON_ID_FIELDS for the scope of tests using this fixture
    original_common_id_fields = copy.deepcopy(COMMON_ID_FIELDS)
    COMMON_ID_FIELDS.extend([id_f for id_f in [TEST_ENTITY_ID_FIELD, ALTERNATIVE_ID_FIELD] if id_f not in COMMON_ID_FIELDS])

    repo = JsonStorageRepository(file_paths_config=file_paths_config, base_data_dir=temp_data_dir)

    yield repo # Provide the repo to the test

    # Restore original COMMON_ID_FIELDS after tests are done
    COMMON_ID_FIELDS.clear()
    COMMON_ID_FIELDS.extend(original_common_id_fields)


@pytest.fixture
async def initialized_repo(json_repository: JsonStorageRepository) -> JsonStorageRepository:
    # Ensure storage is initialized for known entity types
    await json_repository.init_storage_if_needed(TEST_ENTITY_TYPE)
    await json_repository.init_storage_if_needed("gadgets")
    # _load_all_data_on_startup is called in __init__, so this mainly ensures files are created if they weren't
    return json_repository

# --- Test Cases ---

@pytest.mark.asyncio
async def test_repository_initialization_creates_files(
    temp_data_dir: Path, file_paths_config: Dict[str, Path], json_repository: JsonStorageRepository
):
    # json_repository fixture itself calls __init__ which calls _load_all_data_on_startup
    # _load_all_data_on_startup should create files if they don't exist via _ensure_file_exists indirectly
    # (or rather, they are created when _persist_data_to_file is first called if data is added)
    # Let's refine this: init_storage_if_needed is more direct for file creation check

    repo = json_repository # aliasing for clarity

    # Call init_storage_if_needed to ensure files are created if they don't exist
    await repo.init_storage_if_needed(TEST_ENTITY_TYPE)
    await repo.init_storage_if_needed("gadgets")

    widgets_file = temp_data_dir / file_paths_config[TEST_ENTITY_TYPE]
    gadgets_file = temp_data_dir / file_paths_config["gadgets"]

    assert widgets_file.exists(), f"{TEST_ENTITY_TYPE} JSON file was not created."
    assert gadgets_file.exists(), "Gadgets JSON file was not created."

    with open(widgets_file, "r") as f:
        assert json.load(f) == [], "Widgets file should be initialized with an empty list."
    with open(gadgets_file, "r") as f:
        assert json.load(f) == [], "Gadgets file should be initialized with an empty list."

@pytest.mark.asyncio
async def test_repository_initialization_loads_existing_data(
    temp_data_dir: Path, file_paths_config: Dict[str, Path]
):
    # Prepare existing data
    widgets_file = temp_data_dir / file_paths_config[TEST_ENTITY_TYPE]
    existing_widgets_data = [{TEST_ENTITY_ID_FIELD: "widget1", "value": 100}]
    widgets_file.parent.mkdir(parents=True, exist_ok=True)
    with open(widgets_file, "w") as f:
        json.dump(existing_widgets_data, f)

    gadgets_file = temp_data_dir / file_paths_config["gadgets"]
    existing_gadgets_data = [{"gadget_id": "gadgetA", "type": "alpha"}]
    gadgets_file.parent.mkdir(parents=True, exist_ok=True)
    with open(gadgets_file, "w") as f:
        json.dump(existing_gadgets_data, f)

    # Temporarily extend COMMON_ID_FIELDS for this test
    original_common_id_fields = copy.deepcopy(COMMON_ID_FIELDS)
    COMMON_ID_FIELDS.extend([id_f for id_f in [TEST_ENTITY_ID_FIELD, "gadget_id"] if id_f not in COMMON_ID_FIELDS])

    repo = JsonStorageRepository(file_paths_config=file_paths_config, base_data_dir=temp_data_dir)

    # Restore original COMMON_ID_FIELDS
    COMMON_ID_FIELDS.clear()
    COMMON_ID_FIELDS.extend(original_common_id_fields)

    assert repo.in_memory_data[TEST_ENTITY_TYPE] == existing_widgets_data
    assert repo.in_memory_data["gadgets"] == existing_gadgets_data

    # Check indexes
    assert TEST_ENTITY_ID_FIELD in repo.id_indexes[TEST_ENTITY_TYPE]
    assert "widget1" in repo.id_indexes[TEST_ENTITY_TYPE][TEST_ENTITY_ID_FIELD]
    assert repo.id_indexes[TEST_ENTITY_TYPE][TEST_ENTITY_ID_FIELD]["widget1"]["value"] == 100

    assert "gadget_id" in repo.id_indexes["gadgets"] # Assuming gadget_id becomes part of COMMON_ID_FIELDS for this test
    assert "gadgetA" in repo.id_indexes["gadgets"]["gadget_id"]


@pytest.mark.asyncio
async def test_create_entity_new_type(initialized_repo: JsonStorageRepository, temp_data_dir: Path):
    repo = initialized_repo
    entity_type = "new_devices"
    entity_data = {"device_id": "dev001", "model": "SuperDevice"}

    # Ensure TEST_ENTITY_ID_FIELD is part of COMMON_ID_FIELDS for this test run if device_id is to be indexed
    # This is handled by the json_repository fixture's modification of COMMON_ID_FIELDS if device_id is like TEST_ENTITY_ID_FIELD

    created_entity = await repo.create(entity_type, entity_data)

    assert created_entity == entity_data
    assert entity_data in repo.in_memory_data[entity_type]

    # Check if indexed if device_id is in COMMON_ID_FIELDS (it won't be unless added)
    # For this test, let's assume 'device_id' is not in the default COMMON_ID_FIELDS.
    # So, it might not be automatically indexed unless COMMON_ID_FIELDS is manipulated before repo instantiation.
    # The 'json_repository' fixture adds TEST_ENTITY_ID_FIELD, let's assume device_id is not that.
    # If 'device_id' was 'widget_id' (which is TEST_ENTITY_ID_FIELD), it would be indexed.

    # For a truly new ID field like 'device_id', it won't be indexed unless COMMON_ID_FIELDS is updated *before* JsonStorageRepository is instantiated.
    # The current fixture setup for json_repository might already include 'widget_id' in COMMON_ID_FIELDS.
    # Let's test indexing specifically for known ID fields.

    expected_file = temp_data_dir / f"{entity_type}_db.json"
    assert expected_file.exists(), "File for new entity type was not created."
    with open(expected_file, "r") as f:
        data_in_file = json.load(f)
        assert entity_data in data_in_file

@pytest.mark.asyncio
async def test_create_entity_existing_type(initialized_repo: JsonStorageRepository, temp_data_dir: Path, file_paths_config: Dict[str,Path]):
    repo = initialized_repo
    entity_data = {TEST_ENTITY_ID_FIELD: "widget2", "value": 200, "color": "blue"}

    created_entity = await repo.create(TEST_ENTITY_TYPE, entity_data)

    assert created_entity == entity_data
    assert entity_data in repo.in_memory_data[TEST_ENTITY_TYPE]

    # Check index (TEST_ENTITY_ID_FIELD is added to COMMON_ID_FIELDS by the fixture)
    assert "widget2" in repo.id_indexes[TEST_ENTITY_TYPE][TEST_ENTITY_ID_FIELD]
    assert repo.id_indexes[TEST_ENTITY_TYPE][TEST_ENTITY_ID_FIELD]["widget2"]["value"] == 200

    widgets_file = temp_data_dir / file_paths_config[TEST_ENTITY_TYPE]
    with open(widgets_file, "r") as f:
        data_in_file = json.load(f)
        assert entity_data in data_in_file
        assert len(data_in_file) >= 1 # Should contain at least this new one

@pytest.mark.asyncio
async def test_create_entity_with_duplicate_id_raises_error(initialized_repo: JsonStorageRepository):
    repo = initialized_repo
    entity_data1 = {TEST_ENTITY_ID_FIELD: "widget_dup", "value": 300}
    await repo.create(TEST_ENTITY_TYPE, entity_data1)

    entity_data2_dup_id = {TEST_ENTITY_ID_FIELD: "widget_dup", "value": 301}

    with pytest.raises(ValueError) as exc_info:
        await repo.create(TEST_ENTITY_TYPE, entity_data2_dup_id)

    assert "已存在" in str(exc_info.value) or "already exists" in str(exc_info.value).lower()
    assert f"ID 为 'widget_dup' 的实体已存在" in str(exc_info.value) or            f"entity with ID 'widget_dup' already exists" in str(exc_info.value).lower()

    # Also test with another common ID field from the original list like 'id'
    entity_data_id_field = {"id": "common_id_dup", "data": "test"}
    await repo.create(TEST_ENTITY_TYPE, entity_data_id_field)

    entity_data_id_field_dup = {"id": "common_id_dup", "data": "test_dup"}
    with pytest.raises(ValueError) as exc_info_id:
        await repo.create(TEST_ENTITY_TYPE, entity_data_id_field_dup)
    assert "已存在" in str(exc_info_id.value) or "already exists" in str(exc_info_id.value).lower()

# (Existing imports and fixtures should be above this)
# ...

@pytest.mark.asyncio
async def test_get_by_id_success(initialized_repo: JsonStorageRepository):
    repo = initialized_repo
    entity_data = {TEST_ENTITY_ID_FIELD: "widget_get_me", "data": "find me"}
    await repo.create(TEST_ENTITY_TYPE, entity_data)

    # Test with the field added to COMMON_ID_FIELDS by the fixture
    found_entity = await repo.get_by_id(TEST_ENTITY_TYPE, "widget_get_me")
    assert found_entity is not None
    assert found_entity["data"] == "find me"

    # Test with a standard common ID field
    entity_data_std_id = {"id": "std_id_get_me", "data": "standard find"}
    await repo.create(TEST_ENTITY_TYPE, entity_data_std_id)
    found_entity_std = await repo.get_by_id(TEST_ENTITY_TYPE, "std_id_get_me")
    assert found_entity_std is not None
    assert found_entity_std["data"] == "standard find"

@pytest.mark.asyncio
async def test_get_by_id_non_indexed_field_fallback(
    temp_data_dir: Path, file_paths_config: Dict[str, Path]
):
    # This test needs a repo instance where TEST_ENTITY_ID_FIELD is NOT in COMMON_ID_FIELDS during instantiation
    # to test the linear scan fallback.
    original_common_id_fields = copy.deepcopy(COMMON_ID_FIELDS)
    # Ensure TEST_ENTITY_ID_FIELD is not in COMMON_ID_FIELDS for this specific repo instance
    if TEST_ENTITY_ID_FIELD in COMMON_ID_FIELDS:
        COMMON_ID_FIELDS.remove(TEST_ENTITY_ID_FIELD)

    repo = JsonStorageRepository(file_paths_config=file_paths_config, base_data_dir=temp_data_dir)
    await repo.init_storage_if_needed(TEST_ENTITY_TYPE)

    entity_data = {TEST_ENTITY_ID_FIELD: "widget_linear_scan", "data": "found by scan"}
    await repo.create(TEST_ENTITY_TYPE, entity_data) # create will still work

    # Since TEST_ENTITY_ID_FIELD was not in COMMON_ID_FIELDS at repo init, index for it shouldn't exist.
    # However, get_by_id has a fallback to linear scan if the entity_type's index itself is missing,
    # OR if the id_field is not in COMMON_ID_FIELDS (which means it wouldn't have an id_map in id_indexes[entity_type]).
    # The current get_by_id logic iterates through COMMON_ID_FIELDS present in the index.
    # To truly test linear scan for a field *not* in COMMON_ID_FIELDS, that field must be used for lookup,
    # and the primary COMMON_ID_FIELDS must not match.

    # Let's adjust the test: create an entity with a standard ID, then try to fetch it
    # using a value from a non-indexed field, assuming get_by_id could hypothetically support this (it doesn't directly).
    # The current get_by_id only looks up by entity_id against fields in COMMON_ID_FIELDS that are indexed.
    # The "linear scan" in get_by_id is a fallback if the *entire index for the entity type* is missing.

    # Re-think: The linear scan in get_by_id is:
    #   if entity_type not in self.id_indexes: ... iterate self.in_memory_data[entity_type]
    # This happens if _build_id_indexes wasn't called or found no data.

    # To test the specific linear scan part of get_by_id:
    # We need an entity type for which id_indexes[entity_type] does not exist or is empty.
    # This can be simulated by manually removing the index after data is loaded/created.
    repo.id_indexes[TEST_ENTITY_TYPE] = {} # Simulate index is missing for this entity type

    found_entity = await repo.get_by_id(TEST_ENTITY_TYPE, "widget_linear_scan")
    assert found_entity is not None
    assert found_entity["data"] == "found by scan"

    # Restore COMMON_ID_FIELDS
    COMMON_ID_FIELDS.clear()
    COMMON_ID_FIELDS.extend(original_common_id_fields)


@pytest.mark.asyncio
async def test_get_by_id_not_found(initialized_repo: JsonStorageRepository):
    repo = initialized_repo
    found_entity = await repo.get_by_id(TEST_ENTITY_TYPE, "non_existent_widget")
    assert found_entity is None

@pytest.mark.asyncio
async def test_get_all_entities(initialized_repo: JsonStorageRepository):
    repo = initialized_repo
    await repo.create(TEST_ENTITY_TYPE, {TEST_ENTITY_ID_FIELD: "w_all_1", "data": "item1"})
    await repo.create(TEST_ENTITY_TYPE, {TEST_ENTITY_ID_FIELD: "w_all_2", "data": "item2"})

    all_entities = await repo.get_all(TEST_ENTITY_TYPE)
    assert len(all_entities) >= 2 # Can be more if other tests added data

    # Check with skip and limit
    await repo.create(TEST_ENTITY_TYPE, {TEST_ENTITY_ID_FIELD: "w_all_3", "data": "item3"})

    # To make this test more robust, clear data for the entity type first
    repo.in_memory_data[TEST_ENTITY_TYPE] = []
    repo._build_id_indexes(TEST_ENTITY_TYPE) # Rebuild index for empty data
    await repo._persist_data_to_file(TEST_ENTITY_TYPE)


    item1 = {TEST_ENTITY_ID_FIELD: "w_pg_1", "data": "page_item1"}
    item2 = {TEST_ENTITY_ID_FIELD: "w_pg_2", "data": "page_item2"}
    item3 = {TEST_ENTITY_ID_FIELD: "w_pg_3", "data": "page_item3"}
    await repo.create(TEST_ENTITY_TYPE, item1)
    await repo.create(TEST_ENTITY_TYPE, item2)
    await repo.create(TEST_ENTITY_TYPE, item3)

    page1 = await repo.get_all(TEST_ENTITY_TYPE, skip=0, limit=2)
    assert len(page1) == 2
    assert page1[0][TEST_ENTITY_ID_FIELD] == "w_pg_1"
    assert page1[1][TEST_ENTITY_ID_FIELD] == "w_pg_2"

    page2 = await repo.get_all(TEST_ENTITY_TYPE, skip=2, limit=2)
    assert len(page2) == 1
    assert page2[0][TEST_ENTITY_ID_FIELD] == "w_pg_3"

@pytest.mark.asyncio
async def test_update_entity_success(initialized_repo: JsonStorageRepository, temp_data_dir: Path, file_paths_config: Dict[str,Path]):
    repo = initialized_repo
    original_data = {TEST_ENTITY_ID_FIELD: "widget_update_me", "version": 1, "color": "red"}
    await repo.create(TEST_ENTITY_TYPE, original_data)

    update_payload = {"version": 2, "color": "blue"}
    updated_entity = await repo.update(TEST_ENTITY_TYPE, "widget_update_me", update_payload)

    assert updated_entity is not None
    assert updated_entity["version"] == 2
    assert updated_entity["color"] == "blue"
    assert updated_entity[TEST_ENTITY_ID_FIELD] == "widget_update_me" # ID should remain

    # Verify in-memory data
    in_memory_val = await repo.get_by_id(TEST_ENTITY_TYPE, "widget_update_me")
    assert in_memory_val["version"] == 2

    # Verify persisted data
    widgets_file = temp_data_dir / file_paths_config[TEST_ENTITY_TYPE]
    with open(widgets_file, "r") as f:
        data_in_file = json.load(f)
        persisted_item = next(item for item in data_in_file if item[TEST_ENTITY_ID_FIELD] == "widget_update_me")
        assert persisted_item["version"] == 2

@pytest.mark.asyncio
async def test_update_entity_id_modification_raises_error(initialized_repo: JsonStorageRepository):
    repo = initialized_repo
    original_data = {TEST_ENTITY_ID_FIELD: "widget_no_id_change", "value": 10}
    await repo.create(TEST_ENTITY_TYPE, original_data)

    update_payload_id_change = {TEST_ENTITY_ID_FIELD: "new_id_forbidden", "value": 20}

    with pytest.raises(ValueError) as exc_info:
        await repo.update(TEST_ENTITY_TYPE, "widget_no_id_change", update_payload_id_change)

    assert "修改ID字段" in str(exc_info.value) or "modification via update method is prohibited" in str(exc_info.value)

@pytest.mark.asyncio
async def test_update_entity_not_found(initialized_repo: JsonStorageRepository):
    repo = initialized_repo
    updated_entity = await repo.update(TEST_ENTITY_TYPE, "non_existent_for_update", {"data": "new_data"})
    assert updated_entity is None

@pytest.mark.asyncio
async def test_delete_entity_success(initialized_repo: JsonStorageRepository, temp_data_dir: Path, file_paths_config: Dict[str,Path]):
    repo = initialized_repo
    entity_data = {TEST_ENTITY_ID_FIELD: "widget_delete_me", "status": "active"}
    await repo.create(TEST_ENTITY_TYPE, entity_data)

    # Ensure it's there
    assert await repo.get_by_id(TEST_ENTITY_TYPE, "widget_delete_me") is not None

    delete_result = await repo.delete(TEST_ENTITY_TYPE, "widget_delete_me")
    assert delete_result is True
    assert await repo.get_by_id(TEST_ENTITY_TYPE, "widget_delete_me") is None

    # Verify persisted data
    widgets_file = temp_data_dir / file_paths_config[TEST_ENTITY_TYPE]
    with open(widgets_file, "r") as f:
        data_in_file = json.load(f)
        assert not any(item[TEST_ENTITY_ID_FIELD] == "widget_delete_me" for item in data_in_file)

    # Verify index
    assert "widget_delete_me" not in repo.id_indexes[TEST_ENTITY_TYPE][TEST_ENTITY_ID_FIELD]

@pytest.mark.asyncio
async def test_delete_entity_not_found(initialized_repo: JsonStorageRepository):
    repo = initialized_repo
    delete_result = await repo.delete(TEST_ENTITY_TYPE, "non_existent_for_delete")
    assert delete_result is False

@pytest.mark.asyncio
async def test_query_entities(initialized_repo: JsonStorageRepository):
    repo = initialized_repo
    # Clear data for robust query test
    repo.in_memory_data[TEST_ENTITY_TYPE] = []
    repo._build_id_indexes(TEST_ENTITY_TYPE)
    await repo._persist_data_to_file(TEST_ENTITY_TYPE)

    await repo.create(TEST_ENTITY_TYPE, {TEST_ENTITY_ID_FIELD: "q_w1", "color": "red", "active": True})
    await repo.create(TEST_ENTITY_TYPE, {TEST_ENTITY_ID_FIELD: "q_w2", "color": "blue", "active": True})
    await repo.create(TEST_ENTITY_TYPE, {TEST_ENTITY_ID_FIELD: "q_w3", "color": "red", "active": False})

    # Query by color
    red_widgets = await repo.query(TEST_ENTITY_TYPE, {"color": "red"})
    assert len(red_widgets) == 2
    assert all(w["color"] == "red" for w in red_widgets)

    # Query by active status
    active_widgets = await repo.query(TEST_ENTITY_TYPE, {"active": True})
    assert len(active_widgets) == 2
    assert all(w["active"] is True for w in active_widgets)

    # Query by multiple conditions
    red_and_active = await repo.query(TEST_ENTITY_TYPE, {"color": "red", "active": True})
    assert len(red_and_active) == 1
    assert red_and_active[0][TEST_ENTITY_ID_FIELD] == "q_w1"

    # Query with no matches
    green_widgets = await repo.query(TEST_ENTITY_TYPE, {"color": "green"})
    assert len(green_widgets) == 0

    # Query with limit
    limited_red_widgets = await repo.query(TEST_ENTITY_TYPE, {"color": "red"}, limit=1)
    assert len(limited_red_widgets) == 1

@pytest.mark.asyncio
async def test_get_all_entity_types(initialized_repo: JsonStorageRepository):
    repo = initialized_repo
    # From fixture: TEST_ENTITY_TYPE and "gadgets" are initialized
    # If test_create_entity_new_type ran, "new_devices" might be there.
    # Let's make it more deterministic for this test.

    # Create a new repo instance for this test to control entity types precisely
    clean_repo = JsonStorageRepository(file_paths_config=repo.file_paths, base_data_dir=repo.base_data_dir)
    await clean_repo.init_storage_if_needed("typeA")
    await clean_repo.init_storage_if_needed("typeB")

    entity_types = await clean_repo.get_all_entity_types()
    # _load_all_data_on_startup loads types from file_paths_config
    # init_storage_if_needed adds new types if not in file_paths_config

    # The json_repository fixture initializes with TEST_ENTITY_TYPE and "gadgets"
    # So the list should contain at least these.
    # The `clean_repo` above will have 'typeA', 'typeB' PLUS those from file_paths_config
    # because file_paths_config is passed to its constructor.

    # Let's test the `initialized_repo` which is well-defined by its fixture
    entity_types_from_fixture_repo = await repo.get_all_entity_types()
    assert TEST_ENTITY_TYPE in entity_types_from_fixture_repo
    assert "gadgets" in entity_types_from_fixture_repo

    await repo.create("runtime_type", {"id": "rt1"})
    entity_types_after_create = await repo.get_all_entity_types()
    assert "runtime_type" in entity_types_after_create


@pytest.mark.asyncio
async def test_persist_all_data(initialized_repo: JsonStorageRepository, temp_data_dir: Path, file_paths_config: Dict[str, Path]):
    repo = initialized_repo

    # Modify data in memory for two different entity types
    widget_data_mem = {TEST_ENTITY_ID_FIELD: "persist_widget", "data": "memory_only_widget"}
    repo.in_memory_data[TEST_ENTITY_TYPE].append(widget_data_mem) # Add directly to bypass _persist in create
    # Update index manually for this direct memory manipulation
    repo.id_indexes[TEST_ENTITY_TYPE][TEST_ENTITY_ID_FIELD]["persist_widget"] = widget_data_mem


    gadget_data_mem = {"gadget_id": "persist_gadget", "data": "memory_only_gadget"}
    # Ensure 'gadgets' type exists and gadget_id is indexable if not already by fixture
    if "gadgets" not in repo.in_memory_data: repo.in_memory_data["gadgets"] = []
    if "gadgets" not in repo.id_indexes: repo.id_indexes["gadgets"] = {}
    if "gadget_id" not in repo.id_indexes["gadgets"]: repo.id_indexes["gadgets"]["gadget_id"] = {}

    repo.in_memory_data["gadgets"].append(gadget_data_mem)
    repo.id_indexes["gadgets"]["gadget_id"]["persist_gadget"] = gadget_data_mem


    await repo.persist_all_data()

    # Verify persisted data for widgets
    widgets_file = temp_data_dir / file_paths_config[TEST_ENTITY_TYPE]
    with open(widgets_file, "r") as f:
        data_in_file = json.load(f)
        assert any(item[TEST_ENTITY_ID_FIELD] == "persist_widget" for item in data_in_file)

    # Verify persisted data for gadgets
    gadgets_file = temp_data_dir / file_paths_config["gadgets"]
    with open(gadgets_file, "r") as f:
        data_in_file_gadgets = json.load(f)
        assert any(item["gadget_id"] == "persist_gadget" for item in data_in_file_gadgets)
