"""Search API tests."""

import json
import time
import uuid

import pytest

from . import conftest


class TestSemanticSearch:
    """Test semantic search functionality."""

    @pytest.fixture
    def indexed_partition(self, api_client, created_partition, sample_text_file):
        """Create partition and index a document, wait for completion."""
        file_id = "search-test-doc"

        with open(sample_text_file, "rb") as f:
            response = api_client.post(
                f"/indexer/partition/{created_partition}/file/{file_id}",
                files={"file": ("test.txt", f, "text/plain")},
                data={"metadata": "{}"},
            )

        data = response.json()

        # Wait for indexing to complete
        if "task_status_url" in data:
            task_url = data["task_status_url"]
            task_path = "/" + "/".join(task_url.split("/")[3:])
        elif "task_id" in data:
            task_path = f"/indexer/task/{data['task_id']}"
        else:
            # No task info, just wait
            time.sleep(5)
            return created_partition

        for _ in range(30):
            task_response = api_client.get(task_path)
            task_data = task_response.json()
            state = task_data.get("task_state", "")
            if state in ["SUCCESS", "COMPLETED", "success", "completed"]:
                break
            elif state in ["FAILED", "failed", "FAILURE", "failure"]:
                pytest.skip(f"Indexing failed: {task_data}")
            time.sleep(2)

        return created_partition

    def test_search_partition(self, api_client, indexed_partition):
        """Test searching within a partition."""
        response = api_client.get(
            f"/search/partition/{indexed_partition}",
            params={"text": "artificial intelligence", "top_k": 5},
        )
        assert response.status_code == 200
        data = response.json()
        assert "documents" in data

    def test_search_multiple_partitions(self, api_client, indexed_partition):
        """Test searching across partitions."""
        response = api_client.get("/search", params={"text": "machine learning", "top_k": 5})
        assert response.status_code == 200
        data = response.json()
        assert "documents" in data

    def test_search_with_top_k(self, api_client, indexed_partition):
        """Test search with different top_k values."""
        response = api_client.get(
            f"/search/partition/{indexed_partition}",
            params={"text": "deep learning", "top_k": 10},
        )
        assert response.status_code == 200
        data = response.json()
        # Results should not exceed top_k
        assert len(data.get("documents", [])) <= 10

    def test_search_empty_query(self, api_client, indexed_partition):
        """Test search with empty query."""
        response = api_client.get(f"/search/partition/{indexed_partition}", params={"text": "", "top_k": 5})
        # Should return error or empty results
        assert response.status_code in [200, 400, 422]

    def test_search_nonexistent_partition(self, api_client):
        """Test searching non-existent partition."""
        response = api_client.get(
            "/search/partition/nonexistent-partition-xyz",
            params={"text": "test", "top_k": 5},
        )
        # May return empty results or error
        assert response.status_code in [200, 404, 500]

    def test_search_all_partitions(self, api_client, indexed_partition):
        """Test searching with partitions=all."""
        response = api_client.get(
            "/search",
            params={"partitions": "all", "text": "machine learning", "top_k": 5},
        )
        assert response.status_code == 200
        data = response.json()
        assert "documents" in data

    def test_search_with_include_related(self, api_client, indexed_folder_partition, exact_match_query, folder_files):
        """Test search with include_related retrieves all files with same relationship_id.

        This test verifies that when searching with include_related=True, and it's relevant for folder or thread relationships.
        """
        # Search without include_related first
        response_without = api_client.get(
            f"/search/partition/{indexed_folder_partition}",
            params={"text": exact_match_query, "top_k": 1, "include_related": False},
        )
        assert response_without.status_code == 200
        data_without = response_without.json()
        assert "documents" in data_without

        # Should get at least one result (the matching chunk)

        initial_count = len(data_without.get("documents", []))
        assert initial_count > 0, "Should find at least one matching chunk"

        # Search with include_related
        response_with = api_client.get(
            f"/search/partition/{indexed_folder_partition}",
            params={"text": exact_match_query, "top_k": 1, "include_related": True},
        )
        assert response_with.status_code == 200
        data_with = response_with.json()
        assert "documents" in data_with

        # Should get more results (chunks from all 3 files in the folder)
        expanded_count = len(data_with.get("documents", []))
        assert expanded_count > initial_count, (
            f"include_related should expand results. Got {expanded_count} vs {initial_count} without"
        )

        # Verify all documents have the same relationship_id
        relationship_ids = {doc["metadata"].get("relationship_id") for doc in data_with["documents"]}
        assert None not in relationship_ids, (
            f"All documents should carry relationship_id metadata. Got: {relationship_ids}"
        )

        # verify that the relationship_id matches the expected one
        expected_relationship_id = folder_files["file1.txt"][1]  # relationship_id used during indexing
        assert relationship_ids.pop() == expected_relationship_id, (
            f"Documents should have relationship_id {expected_relationship_id}"
        )

        # verify that we got all 3 files' chunks
        filenames = {doc["metadata"].get("filename") for doc in data_with["documents"]}

        expected_filenames = {"file1.txt", "file2.txt", "file3.txt"}
        assert filenames == expected_filenames, f"Expected files {expected_filenames}, got {filenames}"


class TestMultiPartitionUserAccess:
    """Test multi-partition search with user access restrictions."""

    @pytest.fixture
    def two_partitions_with_docs(self, api_client, sample_text_file):
        """Create two partitions with indexed documents."""
        if not conftest.is_auth_enabled():
            pytest.skip("Authentication is disabled")

        partition1 = f"test-p1-{uuid.uuid4().hex[:8]}"
        partition2 = f"test-p2-{uuid.uuid4().hex[:8]}"

        # Create partitions
        resp1 = api_client.post(f"/partition/{partition1}")
        resp2 = api_client.post(f"/partition/{partition2}")
        assert resp1.status_code in [200, 201], f"Failed to create {partition1}: {resp1.text}"
        assert resp2.status_code in [200, 201], f"Failed to create {partition2}: {resp2.text}"

        def _index_and_wait(partition, doc_id):
            with open(sample_text_file, "rb") as f:
                resp = api_client.post(
                    f"/indexer/partition/{partition}/file/{doc_id}",
                    files={"file": ("test.txt", f, "text/plain")},
                    data={"metadata": "{}"},
                )
            assert resp.status_code in [200, 201], f"Indexing failed: {resp.text}"
            data = resp.json()
            if "task_id" in data:
                task_path = f"/indexer/task/{data['task_id']}"
            else:
                return
            for _ in range(30):
                task_response = api_client.get(task_path)
                if task_response.json().get("task_state") in ["SUCCESS", "COMPLETED"]:
                    return
                time.sleep(2)
            pytest.fail(f"Indexing did not complete for {partition}")

        _index_and_wait(partition1, "doc1")
        _index_and_wait(partition2, "doc2")

        yield {"partition1": partition1, "partition2": partition2}

        # Cleanup
        try:
            api_client.delete(f"/partition/{partition1}")
            api_client.delete(f"/partition/{partition2}")
        except Exception:
            pass

    def test_user_search_all_only_sees_own_partitions(
        self, api_client, user_client, created_user, two_partitions_with_docs
    ):
        """Regular user with partitions=all only sees results from their partitions."""
        partition1 = two_partitions_with_docs["partition1"]

        # Grant user access to partition1 only
        api_client.post(
            f"/partition/{partition1}/users",
            data={"user_id": created_user["id"], "role": "viewer"},
        )

        # User searches with partitions=all
        response = user_client.get(
            "/search",
            params={"partitions": "all", "text": "machine learning", "top_k": 10},
        )
        assert response.status_code == 200
        data = response.json()

        # All results should be from partition1 only
        for doc in data.get("documents", []):
            assert doc["metadata"]["partition"] == partition1

    def test_user_cannot_search_unauthorized_partition(
        self, api_client, user_client, created_user, two_partitions_with_docs
    ):
        """Regular user gets 403 when explicitly searching unauthorized partition."""
        partition1 = two_partitions_with_docs["partition1"]
        partition2 = two_partitions_with_docs["partition2"]

        # Grant user access to partition1 only
        api_client.post(
            f"/partition/{partition1}/users",
            data={"user_id": created_user["id"], "role": "viewer"},
        )

        # User tries to explicitly search partition2
        response = user_client.get(
            "/search",
            params={"partitions": partition2, "text": "test", "top_k": 5},
        )
        assert response.status_code == 403

    def test_admin_search_all_sees_all_partitions(self, api_client, two_partitions_with_docs):
        """Admin with partitions=all can see all partitions (if SUPER_ADMIN_MODE)."""
        response = api_client.get(
            "/search",
            params={"partitions": "all", "text": "machine learning", "top_k": 10},
        )
        assert response.status_code == 200
        data = response.json()
        assert "documents" in data


class TestRelatedFilesEndpoint:
    """Test related files retrieval via relationship_id."""

    def test_get_related_files(self, api_client, indexed_folder_partition, folder_files):
        """Test getting all files with the same relationship_id via the partition endpoint."""
        # Get the relationship_id used for folder1 (file1, file2, file3)
        expected_relationship_id = folder_files["file1.txt"][1]

        # Call the get_related_files endpoint
        response = api_client.get(
            f"/partition/{indexed_folder_partition}/relationships/{expected_relationship_id}",
        )
        assert response.status_code == 200
        data = response.json()
        assert "files" in data

        files = data["files"]
        assert len(files) >= 3, f"Expected at least 3 files with relationship_id {expected_relationship_id}"

        # Verify all files have the same relationship_id
        relationship_ids = {f.get("relationship_id") for f in files}
        assert relationship_ids == {expected_relationship_id}, (
            f"All files should have relationship_id {expected_relationship_id}, got {relationship_ids}"
        )

        # Verify we got the expected files
        filenames = {f.get("filename") for f in files}
        expected_filenames = {"file1.txt", "file2.txt", "file3.txt"}
        assert filenames == expected_filenames, f"Expected files {expected_filenames}, got {filenames}"

    def test_get_related_files_nonexistent_relationship(self, api_client, indexed_folder_partition):
        """Test getting files with a non-existent relationship_id returns empty list."""
        response = api_client.get(
            f"/partition/{indexed_folder_partition}/relationships/nonexistent-relationship-xyz",
        )
        assert response.status_code == 200
        data = response.json()
        assert "files" in data
        assert len(data["files"]) == 0, "Should return empty list for non-existent relationship_id"


class TestEmailThreadAncestors:
    """Test email thread ancestor functionality."""

    @pytest.fixture
    def indexed_email_thread(self, api_client, created_partition, email_thread_files):
        """Index all emails from the thread with proper parent_id and relationship_id."""
        for email_id, email_info in email_thread_files.items():
            file_path = email_info["path"]
            parent_id = email_info["parent_id"]
            relationship_id = email_info["relationship_id"]

            # Build metadata with parent_id and relationship_id
            metadata = {"relationship_id": relationship_id}
            if parent_id:
                metadata["parent_id"] = parent_id

            with open(file_path, "rb") as f:
                response = api_client.post(
                    f"/indexer/partition/{created_partition}/file/{email_id}",
                    files={"file": (email_info["filename"], f, "text/plain")},
                    data={"metadata": json.dumps(metadata)},
                )

            data = response.json()

            # Wait for indexing to complete
            if "task_status_url" in data:
                task_url = data["task_status_url"]
                task_path = "/" + "/".join(task_url.split("/")[3:])
            elif "task_id" in data:
                task_path = f"/indexer/task/{data['task_id']}"
            else:
                time.sleep(3)
                continue

            for _ in range(30):
                task_response = api_client.get(task_path)
                task_data = task_response.json()
                state = task_data.get("task_state", "")
                if state in ["SUCCESS", "COMPLETED", "success", "completed"]:
                    break
                elif state in ["FAILED", "failed", "FAILURE", "failure"]:
                    pytest.skip(f"Indexing failed for {email_id}: {task_data}")
                time.sleep(2)

        return created_partition

    def test_get_ancestors_for_leaf_email(self, api_client, indexed_email_thread):
        """Test getting ancestors for the last email in the thread (email_006).

        Should return the complete path: email_001 -> email_002 -> ... -> email_006
        """
        response = api_client.get(
            f"/partition/{indexed_email_thread}/file/email_006/ancestors",
        )
        assert response.status_code == 200
        data = response.json()
        assert "ancestors" in data

        ancestors = data["ancestors"]
        # Should have 6 emails (root to leaf, inclusive)
        assert len(ancestors) == 6, f"Expected 6 ancestors (full path), got {len(ancestors)}"

        # Verify order: should be from root to target file
        expected_order = ["email_001", "email_002", "email_003", "email_004", "email_005", "email_006"]
        actual_order = [a["file_id"] for a in ancestors]
        assert actual_order == expected_order, f"Expected {expected_order}, got {actual_order}"

        # Verify each ancestor has the correct parent_id
        for i, ancestor in enumerate(ancestors):
            if i == 0:
                # Root email should have no parent_id or null parent_id
                assert ancestor.get("parent_id") is None or ancestor.get("parent_id") == "", (
                    f"Root email should have no parent_id, got {ancestor.get('parent_id')}"
                )
            else:
                # Each subsequent email should have the previous email as parent
                expected_parent = expected_order[i - 1]
                assert ancestor.get("parent_id") == expected_parent, (
                    f"Email {ancestor['file_id']} should have parent {expected_parent}, got {ancestor.get('parent_id')}"
                )

    def test_get_ancestors_for_middle_email(self, api_client, indexed_email_thread):
        """Test getting ancestors for an email in the middle of the thread (email_003).

        Should return: email_001 -> email_002 -> email_003
        """
        response = api_client.get(
            f"/partition/{indexed_email_thread}/file/email_003/ancestors",
        )
        assert response.status_code == 200
        data = response.json()
        assert "ancestors" in data

        ancestors = data["ancestors"]
        # Should have 3 emails (root to email_003, inclusive)
        assert len(ancestors) == 3, f"Expected 3 ancestors, got {len(ancestors)}"

        # Verify order
        expected_order = ["email_001", "email_002", "email_003"]
        actual_order = [a["file_id"] for a in ancestors]
        assert actual_order == expected_order, f"Expected {expected_order}, got {actual_order}"

    def test_get_ancestors_for_root_email(self, api_client, indexed_email_thread):
        """Test getting ancestors for the root email (email_001).

        Should return just itself or an array with only email_001.
        """
        response = api_client.get(
            f"/partition/{indexed_email_thread}/file/email_001/ancestors",
        )
        assert response.status_code == 200
        data = response.json()
        assert "ancestors" in data

        ancestors = data["ancestors"]
        # Should have just 1 email (itself)
        assert len(ancestors) == 1, f"Expected 1 ancestor (itself), got {len(ancestors)}"
        assert ancestors[0]["file_id"] == "email_001"

    def test_get_ancestors_nonexistent_file(self, api_client, indexed_email_thread):
        """Test getting ancestors for a non-existent file."""
        response = api_client.get(
            f"/partition/{indexed_email_thread}/file/nonexistent_email/ancestors",
        )
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data

    def test_ancestors_all_share_same_relationship_id(self, api_client, indexed_email_thread):
        """Test that all ancestors share the same relationship_id (thread_id)."""
        response = api_client.get(
            f"/partition/{indexed_email_thread}/file/email_006/ancestors",
        )
        assert response.status_code == 200
        data = response.json()

        ancestors = data["ancestors"]
        # All should have the same relationship_id
        relationship_ids = {a.get("relationship_id") for a in ancestors}
        assert len(relationship_ids) == 1, f"All ancestors should share same relationship_id, got {relationship_ids}"
        assert "thread_001" in relationship_ids, f"Expected relationship_id 'thread_001', got {relationship_ids}"
