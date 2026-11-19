
from unittest.mock import patch

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse

from .models import (
    ResearchResource,
    SavedResearchItem,
    ResearchCollection,
    CollectionItem,
)

User = get_user_model()


class ResearchLibraryTests(TestCase):

    @classmethod
    def setUpTestData(cls):

        cls.member_a = User.objects.create_user(
            username="library_student_a",
            email="library_a@example.com",
            password="TestPass123!"
        )

        cls.member_b = User.objects.create_user(
            username="library_student_b",
            email="library_b@example.com",
            password="TestPass123!"
        )

        cls.resource = ResearchResource.objects.create(
            title="Machine Learning Fundamentals",
            description="Introduction to machine learning.",
            resource_type="link",
            url="https://example.org/ml",
            uploaded_by=cls.member_a
        )

        cls.saved_item = SavedResearchItem.objects.create(
            user=cls.member_a,
            resource=cls.resource,
            private_notes="My original private note."
        )

    # =====================================
    # TEST 1: VIEW RESEARCH LIBRARY
    # =====================================

    def test_member_can_view_research_library(self):

        self.client.force_login(self.member_a)

        response = self.client.get(
            reverse("research_library:library_home")
        )

        self.assertEqual(response.status_code, 200)

        self.assertTemplateUsed(
            response,
            "research_library/library_home.html"
        )

    # =====================================
    # TEST 2: SAVE RESOURCE USING URL
    # =====================================

    def test_member_can_save_resource_using_url(self):

        self.client.force_login(self.member_b)

        response = self.client.post(
            reverse("research_library:save"),
            {
                "source_type": "url",
                "identifier": "https://example.org/new-paper",
                "title": "New Research Paper",
                "private_notes": "Review this paper."
            }
        )

        self.assertEqual(response.status_code, 302)

        resource = ResearchResource.objects.get(
            url="https://example.org/new-paper"
        )

        saved_item = SavedResearchItem.objects.get(
            user=self.member_b,
            resource=resource
        )

        self.assertEqual(
            saved_item.private_notes,
            "Review this paper."
        )

    # =====================================
    # TEST 3: PREVENT DUPLICATE URL SAVES
    # =====================================

    def test_duplicate_url_does_not_create_duplicate_record(self):

        self.client.force_login(self.member_a)

        response = self.client.post(
            reverse("research_library:save"),
            {
                "source_type": "url",
                "identifier": "https://example.org/ml",
                "title": "Machine Learning Fundamentals",
                "private_notes": ""
            }
        )

        self.assertEqual(response.status_code, 302)

        self.assertEqual(
            ResearchResource.objects.filter(
                url="https://example.org/ml"
            ).count(),
            1
        )

        self.assertEqual(
            SavedResearchItem.objects.filter(
                user=self.member_a,
                resource=self.resource
            ).count(),
            1
        )

    # =====================================
    # TEST 4: SAVE RESOURCE USING DOI
    # =====================================

    @patch(
        "research_library.services.fetch_crossref_metadata"
    )
    def test_member_can_save_resource_using_doi(
        self,
        mock_crossref
    ):

        mock_crossref.return_value = {
            "title": "Advanced Machine Learning",
            "description": "Research publication abstract.",
            "url": "https://doi.org/10.1234/test"
        }

        self.client.force_login(self.member_a)

        response = self.client.post(
            reverse("research_library:save"),
            {
                "source_type": "doi",
                "identifier": "10.1234/test",
                "title": "",
                "private_notes": "Read the methodology."
            }
        )

        self.assertEqual(response.status_code, 302)

        resource = ResearchResource.objects.get(
            doi="10.1234/test"
        )

        self.assertEqual(
            resource.title,
            "Advanced Machine Learning"
        )

        self.assertTrue(
            SavedResearchItem.objects.filter(
                user=self.member_a,
                resource=resource
            ).exists()
        )

    # =====================================
    # TEST 5: SAVE RESOURCE USING ARXIV ID
    # =====================================

    @patch(
        "research_library.services.fetch_arxiv_metadata"
    )
    def test_member_can_save_resource_using_arxiv(
        self,
        mock_arxiv
    ):

        mock_arxiv.return_value = {
            "title": "Research on Neural Networks",
            "description": "Neural network research abstract.",
            "url": "https://arxiv.org/abs/2501.12345"
        }

        self.client.force_login(self.member_b)

        response = self.client.post(
            reverse("research_library:save"),
            {
                "source_type": "arxiv",
                "identifier": "2501.12345",
                "title": "",
                "private_notes": "Study this paper."
            }
        )

        self.assertEqual(response.status_code, 302)

        resource = ResearchResource.objects.get(
            arxiv_id="2501.12345"
        )

        self.assertEqual(
            resource.title,
            "Research on Neural Networks"
        )

        self.assertTrue(
            SavedResearchItem.objects.filter(
                user=self.member_b,
                resource=resource
            ).exists()
        )

    # =====================================
    # TEST 6: MULTIPLE MEMBERS SHARE RESOURCE
    # =====================================

    def test_two_members_can_save_same_resource(self):

        SavedResearchItem.objects.create(
            user=self.member_b,
            resource=self.resource
        )

        self.assertEqual(
            SavedResearchItem.objects.filter(
                resource=self.resource
            ).count(),
            2
        )

        self.assertEqual(
            ResearchResource.objects.filter(
                url="https://example.org/ml"
            ).count(),
            1
        )

    # =====================================
    # TEST 7: CREATE PERSONAL COLLECTION
    # =====================================

    def test_member_can_create_collection(self):

        self.client.force_login(self.member_a)

        response = self.client.post(
            reverse("research_library:create_collection"),
            {
                "name": "Machine Learning Papers",
                "description": "My ML research collection."
            }
        )

        self.assertEqual(response.status_code, 302)

        collection = ResearchCollection.objects.get(
            owner=self.member_a,
            name="Machine Learning Papers"
        )

        self.assertEqual(
            collection.description,
            "My ML research collection."
        )

    # =====================================
    # TEST 8: ADD SAVED ITEM TO COLLECTION
    # =====================================

    def test_member_can_add_item_to_collection(self):

        collection = ResearchCollection.objects.create(
            owner=self.member_a,
            name="My Research"
        )

        self.client.force_login(self.member_a)

        response = self.client.post(
            reverse("research_library:add_to_collection"),
            {
                "collection": collection.id,
                "saved_item": self.saved_item.id
            }
        )

        self.assertEqual(response.status_code, 302)

        self.assertTrue(
            CollectionItem.objects.filter(
                collection=collection,
                saved_item=self.saved_item
            ).exists()
        )

    # =====================================
    # TEST 9: PREVENT CROSS-MEMBER COLLECTION ACCESS
    # =====================================

    def test_member_cannot_add_another_members_saved_item(self):

        collection = ResearchCollection.objects.create(
            owner=self.member_a,
            name="Private Collection"
        )

        other_resource = ResearchResource.objects.create(
            title="Other Member Research",
            resource_type="link",
            url="https://example.org/other",
            uploaded_by=self.member_b
        )

        other_saved_item = SavedResearchItem.objects.create(
            user=self.member_b,
            resource=other_resource
        )

        self.client.force_login(self.member_a)

        response = self.client.post(
            reverse("research_library:add_to_collection"),
            {
                "collection": collection.id,
                "saved_item": other_saved_item.id
            }
        )

        self.assertEqual(response.status_code, 302)

        self.assertFalse(
            CollectionItem.objects.filter(
                collection=collection,
                saved_item=other_saved_item
            ).exists()
        )

    # =====================================
    # TEST 10: REMOVE ITEM FROM COLLECTION
    # =====================================

    def test_member_can_remove_item_from_collection(self):

        collection = ResearchCollection.objects.create(
            owner=self.member_a,
            name="Test Collection"
        )

        collection_item = CollectionItem.objects.create(
            collection=collection,
            saved_item=self.saved_item
        )

        self.client.force_login(self.member_a)

        response = self.client.post(
            reverse(
                "research_library:remove_from_collection",
                args=[collection_item.id]
            )
        )

        self.assertEqual(response.status_code, 302)

        self.assertFalse(
            CollectionItem.objects.filter(
                id=collection_item.id
            ).exists()
        )

        # The personal saved item must remain
        self.assertTrue(
            SavedResearchItem.objects.filter(
                id=self.saved_item.id
            ).exists()
        )

    # =====================================
    # TEST 11: UPDATE PRIVATE NOTES
    # =====================================

    def test_member_can_update_private_notes(self):

        self.client.force_login(self.member_a)

        response = self.client.post(
            reverse(
                "research_library:update_note",
                args=[self.saved_item.id]
            ),
            {
                "private_notes": "Updated private research notes."
            }
        )

        self.assertEqual(response.status_code, 302)

        self.saved_item.refresh_from_db()

        self.assertEqual(
            self.saved_item.private_notes,
            "Updated private research notes."
        )

    # =====================================
    # TEST 12: PRIVATE NOTES ARE PROTECTED
    # =====================================

    def test_other_member_cannot_update_private_notes(self):

        self.client.force_login(self.member_b)

        response = self.client.post(
            reverse(
                "research_library:update_note",
                args=[self.saved_item.id]
            ),
            {
                "private_notes": "Unauthorized note change."
            }
        )

        self.assertEqual(response.status_code, 404)

        self.saved_item.refresh_from_db()

        self.assertEqual(
            self.saved_item.private_notes,
            "My original private note."
        )

    # =====================================
    # TEST 13: UNIVERSITY-WIDE SAVE COUNT
    # =====================================

    def test_library_displays_distinct_member_save_count(self):

        SavedResearchItem.objects.create(
            user=self.member_b,
            resource=self.resource
        )

        self.client.force_login(self.member_a)

        response = self.client.get(
            reverse("research_library:library_home")
        )

        self.assertEqual(response.status_code, 200)

        resource_in_context = next(
            resource
            for resource in response.context["library_resources"]
            if resource.id == self.resource.id
        )

        self.assertEqual(
            resource_in_context.member_save_count,
            2
        )

    # =====================================
    # TEST 14: SEARCH RESEARCH SOURCES
    # =====================================

    @patch(
        "research_library.views.search_research_sources"
    )
    def test_member_can_search_research_sources(
        self,
        mock_search
    ):

        mock_search.return_value = (
            [
                {
                    "provider": "Crossref",
                    "source_type": "doi",
                    "identifier": "10.1234/search",
                    "title": "Search Result Research",
                    "description": "Academic publication.",
                    "url": "https://doi.org/10.1234/search",
                }
            ],
            []
        )

        self.client.force_login(self.member_a)

        response = self.client.get(
            reverse("research_library:library_home"),
            {
                "query": "machine learning"
            }
        )

        self.assertEqual(response.status_code, 200)

        mock_search.assert_called_once_with(
            "machine learning"
        )

        self.assertTrue(
            response.context["search_performed"]
        )

        self.assertEqual(
            len(response.context["search_results"]),
            1
        )

    # =====================================
    # TEST 15: ANONYMOUS ACCESS RESTRICTIONS
    # =====================================

    def test_anonymous_members_cannot_access_library(self):

        response = self.client.get(
            reverse("research_library:library_home")
        )

        self.assertEqual(response.status_code, 302)

        response = self.client.post(
            reverse("research_library:save"),
            {
                "source_type": "url",
                "identifier": "https://example.org/new",
                "title": "New Resource"
            }
        )

        self.assertEqual(response.status_code, 302)
