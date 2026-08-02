import json
import unittest
from unittest.mock import patch

from biomed_workbench.services.public_databases import (
    HTTPResponse,
    PublicDatabaseError,
    PublicJSONClient,
    alphafold_structure_records,
    clinical_trial_records,
    ncbi_gene_orthologs,
    enrichr_gene_set_library,
    ensembl_gene_lookup,
    archs4_expression_atlas,
    hpo_term_records,
    iupred2a_disorder_prediction,
    uniprot_protein_record,
    uniprot_to_ensembl_gene_mapping,
    quickgo_term_records,
    reactome_pathway_record,
    reactome_gene_set_overrepresentation,
    opentargets_target_disease_evidence,
    gnomad_gene_constraint_evidence,
    cbioportal_study_evidence,
    cbioportal_gene_mutation_evidence,
    cbioportal_gene_copy_number_evidence,
    preprint_record,
    pubchem_compound,
    rcsb_ligand_records,
    rcsb_polymer_entity_records,
    rcsb_structure_search,
    rcsb_structure_records,
    resolve_citation_record,
)
from biomed_workbench.capabilities.clinical import cbioportal_copy_number_audit_input, cbioportal_copy_number_coverage_audit, copy_number_event_summary


class FixtureTransport:
    def __init__(self, routes):
        self.routes = routes
        self.urls = []

    def __call__(self, url, _headers, _timeout):
        self.urls.append(url)
        for fragment, response in self.routes:
            if fragment in url:
                payload = response() if callable(response) else response
                if isinstance(payload, HTTPResponse):
                    return payload
                return HTTPResponse(200, {"Content-Type": "application/json"}, json.dumps(payload).encode())
        raise AssertionError(f"unmatched fixture URL: {url}")


class FixturePostTransport:
    def __init__(self, routes):
        self.routes = routes
        self.urls = []

    def __call__(self, url, _headers, _body, _timeout):
        self.urls.append(url)
        for fragment, payload in self.routes:
            if fragment in url:
                return HTTPResponse(200, {"Content-Type": "application/json"}, json.dumps(payload).encode())
        raise AssertionError(f"unmatched fixture POST URL: {url}")


class PublicDatabaseTests(unittest.TestCase):
    def client(self, routes):
        return PublicJSONClient(transport=FixtureTransport(routes), retries=0, sleeper=lambda _: None)

    def test_gnomad_gene_constraint_is_bounded_and_source_preserved(self):
        client = PublicJSONClient(
            post_transport=FixturePostTransport([("gnomad.broadinstitute.org/api", {"data": {"gene": {"gene_id": "ENSG00000141510", "symbol": "TP53", "chrom": "17", "start": 7661779, "stop": 7687546, "gnomad_constraint": {"exp_lof": 100.0, "obs_lof": 20, "oe_lof": 0.2, "oe_lof_lower": 0.1, "oe_lof_upper": 0.3, "oe_lof_percentile": 2, "pli": 0.99, "flags": []}}}})]),
            retries=0, sleeper=lambda _: None,
        )
        result = gnomad_gene_constraint_evidence("TP53", client=client)
        self.assertTrue(result["found"])
        self.assertEqual(result["gene"]["gene_id"], "ENSG00000141510")
        self.assertEqual(result["constraint"]["oe_lof_upper"], 0.3)

    def test_cbioportal_study_record_preserves_exact_identity_and_assay_counts(self):
        payload = {"studyId": "msk_impact_2017", "cancerTypeId": "mixed", "name": "MSK-IMPACT cohort", "description": "Targeted sequencing.", "publicStudy": True, "pmid": "28481359", "citation": "Zehir et al.", "allSampleCount": 10945, "sequencedSampleCount": 10945, "cnaSampleCount": 10945, "mrnaRnaSeqSampleCount": 0, "referenceGenome": "hg19", "treatmentCount": 0, "structuralVariantCount": 1667, "cancerType": {"id": "mixed", "name": "Mixed Cancer Types", "shortName": "MIXED", "parent": "other"}, "readPermission": True}
        result = cbioportal_study_evidence("msk_impact_2017", client=self.client([("/api/studies/msk_impact_2017", payload)]))
        self.assertTrue(result["found"])
        self.assertEqual(result["study"]["study_id"], "msk_impact_2017")
        self.assertEqual(result["study"]["sample_counts"]["sequencedSampleCount"], 10945)

    def test_cbioportal_gene_mutations_resolve_profile_and_detect_bounded_truncation(self):
        mutation = {"studyId": "msk_impact_2017", "molecularProfileId": "msk_impact_2017_mutations", "sampleId": "P-0001-T01", "entrezGeneId": 7157, "startPosition": 7577539, "endPosition": 7577539, "referenceAllele": "G", "variantAllele": "A", "ncbiBuild": "GRCh37", "variantType": "SNP", "mutationType": "Missense_Mutation", "proteinChange": "R248W", "refseqMrnaId": "NM_001126112.2", "tumorAltCount": 61, "tumorRefCount": 131, "chr": "17"}
        routes = [
            ("/api/genes/TP53", {"entrezGeneId": 7157, "hugoGeneSymbol": "TP53"}),
            ("/mutations", [mutation, {**mutation, "sampleId": "P-0002-T01", "startPosition": 7578406, "endPosition": 7578406, "proteinChange": "R175H"}]),
            ("/molecular-profiles", [{"studyId": "msk_impact_2017", "molecularAlterationType": "MUTATION_EXTENDED", "molecularProfileId": "msk_impact_2017_mutations", "name": "Mutations", "datatype": "MAF"}]),
            ("/sample-lists", [{"studyId": "msk_impact_2017", "category": "all_cases_with_mutation_data", "sampleListId": "msk_impact_2017_sequenced", "name": "Mutation samples", "description": "All sequenced samples"}]),
        ]
        def post(url, _headers, body, _timeout):
            self.assertIn("/mutations/fetch?projection=SUMMARY", url)
            self.assertEqual(json.loads(body), {"entrezGeneIds": [7157], "sampleListId": "msk_impact_2017_sequenced"})
            return HTTPResponse(200, {"Content-Type": "application/json"}, json.dumps([mutation, {**mutation, "sampleId": "P-0002-T01", "startPosition": 7578406, "endPosition": 7578406, "proteinChange": "R175H"}]).encode())
        client = PublicJSONClient(transport=FixtureTransport([route for route in routes if route[0] != "/mutations"]), post_transport=post, retries=0, sleeper=lambda _: None)
        result = cbioportal_gene_mutation_evidence("msk_impact_2017", "TP53", max_records=1, client=client)
        self.assertTrue(result["found"])
        self.assertEqual(result["resolution_status"], "resolved")
        self.assertEqual(result["returned_count"], 1)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["records"][0]["protein_change"], "R248W")

    def test_cbioportal_copy_number_uses_post_gene_filter_and_labels_events(self):
        routes = [
            ("/api/genes/TP53", {"entrezGeneId": 7157, "hugoGeneSymbol": "TP53"}),
            ("/molecular-profiles", [{"studyId": "msk_impact_2017", "molecularAlterationType": "COPY_NUMBER_ALTERATION", "datatype": "DISCRETE", "molecularProfileId": "msk_impact_2017_cna", "name": "CNA"}]),
            ("/sample-lists", [{"studyId": "msk_impact_2017", "category": "all_cases_with_cna_data", "sampleListId": "msk_impact_2017_cna", "name": "CNA samples"}]),
        ]
        records = [{"studyId": "msk_impact_2017", "molecularProfileId": "msk_impact_2017_cna", "sampleId": "P-1", "entrezGeneId": 7157, "alteration": -2}, {"studyId": "msk_impact_2017", "molecularProfileId": "msk_impact_2017_cna", "sampleId": "P-2", "entrezGeneId": 7157, "alteration": 2}]
        def post(url, _headers, body, _timeout):
            self.assertIn("/discrete-copy-number/fetch?discreteCopyNumberEventType=HOMDEL_AND_AMP&projection=SUMMARY", url)
            self.assertEqual(json.loads(body), {"entrezGeneIds": [7157], "sampleListId": "msk_impact_2017_cna"})
            return HTTPResponse(200, {"Content-Type": "application/json"}, json.dumps(records).encode())
        client = PublicJSONClient(transport=FixtureTransport(routes), post_transport=post, retries=0, sleeper=lambda _: None)
        result = cbioportal_gene_copy_number_evidence("msk_impact_2017", "TP53", max_records=1, client=client)
        self.assertTrue(result["found"])
        self.assertEqual(result["service_record_count"], 2)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["records"][0]["alteration_label"], "homozygous_deletion")

    def test_copy_number_summary_blocks_incomplete_cohort_prevalence(self):
        result = copy_number_event_summary([{"sample_id": "S1", "alteration": -2}, {"sample_id": "S2", "alteration": 2}], 3)
        self.assertEqual(result["quality_status"], "incomplete_cohort_coverage")
        self.assertEqual(result["event_counts"]["homozygous_deletion"], 1)
        self.assertAlmostEqual(result["event_fractions_of_declared_cohort"]["amplification"], 1 / 3)

    def test_cbioportal_copy_number_adapter_rejects_truncation_and_preserves_denominator(self):
        evidence = {"found": True, "truncated": False, "study_id": "study", "gene_symbol": "TP53", "sample_list": {"id": "study_cna", "sample_count": 2}, "records": [{"sample_id": "S1", "alteration": -2}, {"sample_id": "S2", "alteration": 2}]}
        adapted = cbioportal_copy_number_audit_input(evidence)
        self.assertEqual(adapted["sample_count"], 2)
        self.assertEqual(adapted["records"][1]["alteration"], 2)
        with self.assertRaises(ValueError):
            cbioportal_copy_number_audit_input({**evidence, "truncated": True})
        composed = cbioportal_copy_number_coverage_audit(evidence)
        self.assertEqual(composed["summary"]["quality_status"], "eligible_for_descriptive_cna_summary")

    def test_enrichr_library_snapshot_is_bounded_and_preserves_membership(self):
        client = self.client([("Enrichr/geneSetLibrary", {"Toy_Library": {"libraryName": "Toy_Library", "isFuzzy": False, "terms": {"Term B": {"TP53": 1.0, "BRCA1": 1.0}, "Term A": {"EGFR": 1.0}}}})])
        result = enrichr_gene_set_library("Toy_Library", max_terms=1, max_members_per_term=1, client=client)
        self.assertEqual(result["term_count"], 2)
        self.assertEqual(result["returned_term_count"], 1)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["terms"][0]["term"], "Term A")
        self.assertEqual(result["terms"][0]["genes"], ["EGFR"])

    def test_archs4_expression_rejects_hierarchy_rows_and_orders_numeric_observations(self):
        payload = (
            "id,min,q1,median,q3,max,color\n"
            "System,,,,,,\n"
            "Lung,0.1,2.0,5.0,8.0,12.0,#aaa\n"
            "Kidney,0.1,3.0,9.0,10.0,15.0,#bbb\n"
            "Malformed,4.0,2.0,3.0,5.0,7.0,#ccc\n"
        )
        client = self.client([("loadExpressionTissue.php", HTTPResponse(200, {"Content-Type": "text/csv"}, payload.encode()))])
        result = archs4_expression_atlas("ace2", "human", "tissue", 1, client=client)
        self.assertEqual(result["gene_symbol"], "ACE2")
        self.assertEqual(result["observation_count"], 2)
        self.assertEqual(result["hierarchy_row_count"], 1)
        self.assertEqual(result["malformed_row_count"], 1)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["observations"][0]["label"], "Kidney")

    def test_hpo_terms_preserve_exact_ids_and_not_found_state(self):
        client = self.client([("/api/hp/terms/HP%3A0001250", {"id": "HP:0001250", "name": "Seizure", "definition": "A clinical event.", "synonyms": ["Seizures", "Epileptic seizure"], "descendantCount": 12}), ("/api/hp/terms/HP%3A9999999", HTTPResponse(404, {}, b"{}"))])
        result = hpo_term_records(["HP:0001250", "HP:9999999"], client=client)
        self.assertEqual(result["returned_count"], 1)
        self.assertEqual(result["records"][0]["name"], "Seizure")
        self.assertEqual(result["not_found_ids"], ["HP:9999999"])

    def test_uniprot_protein_record_preserves_identity_and_sequence_metadata(self):
        payload = {"primaryAccession":"P04637","uniProtkbId":"P53_HUMAN","entryType":"UniProtKB reviewed (Swiss-Prot)","proteinDescription":{"recommendedName":{"fullName":{"value":"Cellular tumor antigen p53"}}},"genes":[{"geneName":{"value":"TP53"}}],"organism":{"scientificName":"Homo sapiens","taxonId":9606},"sequence":{"length":393,"molWeight":43653,"crc64":"AD5C","md5":"C133"}}
        result = uniprot_protein_record("p04637", client=self.client([("/uniprotkb/P04637.json", payload)]))
        self.assertEqual(result["accession"], "P04637")
        self.assertEqual(result["gene_names"], ["TP53"])
        self.assertEqual(result["sequence"]["length"], 393)

    def test_uniprot_to_ensembl_mapping_preserves_unmapped_accessions(self):
        def post(url, _headers, body, _timeout):
            self.assertIn("/idmapping/run", url)
            self.assertEqual(body, b"from=UniProtKB_AC-ID&to=Ensembl&ids=P04637%2CQ99999")
            return HTTPResponse(200, {}, b'{"jobId":"job-1"}')
        client = PublicJSONClient(transport=FixtureTransport([("/idmapping/status/job-1", {"results": [{"from": "P04637", "to": "ENSG00000141510.20"}]})]), post_transport=post, retries=0, sleeper=lambda _: None)
        result = uniprot_to_ensembl_gene_mapping(["P04637", "Q99999"], client=client)
        self.assertEqual(result["mapped_count"], 1)
        self.assertEqual(result["unmapped_accessions"], ["Q99999"])
        self.assertEqual(result["records"][0]["ensembl_gene_ids"], ["ENSG00000141510.20"])

    def test_quickgo_terms_preserve_exact_ids_aspect_and_not_found_state(self):
        payload = {"numberOfHits":1,"results":[{"id":"GO:0006915","name":"apoptotic process","aspect":"biological_process","isObsolete":False,"definition":{"text":"A programmed cell death process."},"synonyms":[{"name":"apoptosis","type":"narrow"}]}]}
        client = self.client([("/QuickGO/services/ontology/go/terms/GO%3A0006915", payload), ("/QuickGO/services/ontology/go/terms/GO%3A9999999", HTTPResponse(404, {}, b"{}"))])
        result = quickgo_term_records(["GO:0006915", "GO:9999999"], client=client)
        self.assertEqual(result["records"][0]["aspect"], "biological_process")
        self.assertEqual(result["not_found_ids"], ["GO:9999999"])

    def test_ensembl_gene_lookup_preserves_assembly_coordinates_and_not_found_state(self):
        payload = {"id": "ENSG00000141510", "display_name": "TP53", "species": "homo_sapiens", "assembly_name": "GRCh38", "seq_region_name": "17", "start": 7661779, "end": 7687546, "strand": -1, "biotype": "protein_coding", "canonical_transcript": "ENST00000269305.9", "version": 21}
        client = self.client([("/lookup/symbol/homo_sapiens/TP53", payload), ("/lookup/symbol/homo_sapiens/NOGENE", HTTPResponse(404, {}, b"{}"))])
        result = ensembl_gene_lookup("tp53", client=client)
        missing = ensembl_gene_lookup("nogene", client=client)
        self.assertEqual(result["record"]["assembly_name"], "GRCh38")
        self.assertEqual(result["record"]["ensembl_gene_id"], "ENSG00000141510")
        self.assertFalse(missing["found"])

    def test_reactome_pathway_record_preserves_exact_identity_and_go_context(self):
        payload = {"stId": "R-HSA-109581", "stIdVersion": "R-HSA-109581.6", "displayName": "Apoptosis", "speciesName": "Homo sapiens", "schemaClass": "Pathway", "releaseDate": "2004-09-20", "isInDisease": False, "isInferred": False, "goBiologicalProcess": {"accession": "0006915", "displayName": "apoptotic process"}}
        client = self.client([("/ContentService/data/query/R-HSA-109581", payload), ("/ContentService/data/query/R-HSA-999999", HTTPResponse(404, {}, b"{}"))])
        result = reactome_pathway_record("R-HSA-109581", client=client)
        missing = reactome_pathway_record("R-HSA-999999", client=client)
        self.assertEqual(result["record"]["go_biological_process"]["accession"], "GO:0006915")
        self.assertFalse(missing["found"])

    def test_reactome_overrepresentation_preserves_mapping_and_ranked_pathways(self):
        payload = {"summary": {"type": "OVERREPRESENTATION", "token": "bounded-token"}, "identifiersNotFound": 1, "pathways": [{"stId": "R-HSA-6796648", "name": "TP53 repair", "species": {"name": "Homo sapiens"}, "inDisease": False, "entities": {"total": 86, "found": 4, "pValue": 2.2e-6, "fdr": 5.8e-4}}, {"stId": "R-HSA-000001", "name": "Later", "entities": {"total": 10, "found": 1, "pValue": 0.02, "fdr": 0.03}}]}
        def post(url, _headers, body, _timeout):
            self.assertIn("AnalysisService/identifiers", url)
            self.assertEqual(body, b"TP53\nBRCA1\n")
            return HTTPResponse(200, {"Content-Type": "application/json"}, json.dumps(payload).encode())
        result = reactome_gene_set_overrepresentation(["TP53", "BRCA1"], max_pathways=1, client=PublicJSONClient(post_transport=post, retries=0, sleeper=lambda _: None))
        self.assertEqual(result["unmapped_identifier_count"], 1)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["pathways"][0]["stable_id"], "R-HSA-6796648")

    def test_opentargets_target_disease_evidence_preserves_source_rows_and_truncation(self):
        response = {"data": {"disease": {"id": "MONDO_0007254", "name": "breast cancer", "evidences": {"count": 2, "rows": [{"datasourceId": "cancer_gene_census", "datatypeId": "somatic_mutation", "score": 1, "targetFromSourceId": "ENSG00000141510", "studyId": None, "literature": ["22722193"]}]}}}}
        def post(url, _headers, body, _timeout):
            self.assertIn("/api/v4/graphql", url)
            request = json.loads(body)
            self.assertEqual(request["variables"]["geneId"], "ENSG00000141510")
            return HTTPResponse(200, {}, json.dumps(response).encode())
        result = opentargets_target_disease_evidence("ENSG00000141510", "MONDO_0007254", max_records=1, client=PublicJSONClient(post_transport=post, retries=0, sleeper=lambda _: None))
        self.assertEqual(result["disease_name"], "breast cancer")
        self.assertTrue(result["truncated"])
        self.assertEqual(result["evidence"][0]["datasource_id"], "cancer_gene_census")

    def test_citation_resolution_preserves_cross_source_disagreement(self):
        client = self.client(
            [
                (
                    "api.crossref.org/v1/works/10.1000%2Ftest",
                    {
                        "message": {
                            "DOI": "10.1000/test",
                            "title": ["Registered title"],
                            "type": "journal-article",
                            "publisher": "Example Publisher",
                            "container-title": ["Example Journal"],
                            "published": {"date-parts": [[2025, 1, 2]]},
                            "author": [{"given": "A", "family": "Author"}],
                            "is-referenced-by-count": 4,
                            "relation": {},
                            "update-to": [],
                        }
                    },
                ),
                (
                    "europepmc/webservices/rest/search",
                    {
                        "resultList": {
                            "result": [
                                {"doi": "10.1000/test", "title": "Repository title", "pmid": "123"},
                                {"doi": "10.1000/other", "title": "Wrong DOI"},
                            ]
                        }
                    },
                ),
            ]
        )
        result = resolve_citation_record("https://doi.org/10.1000/TEST", client=client)
        self.assertEqual(result["query"]["doi"], "10.1000/test")
        self.assertEqual(result["crossref"]["title"], "Registered title")
        self.assertEqual([record["pmid"] for record in result["europe_pmc_records"]], ["123"])
        self.assertEqual(result["agreement"]["europe_pmc_exact_doi_matches"], 1)
        self.assertIn("disagree", result["limitations"][0])

    def test_preprint_versions_are_retained_and_sorted(self):
        client = self.client(
            [
                (
                    "api.biorxiv.org/details/biorxiv/10.1101/2024.01.01.123456/na/json",
                    {
                        "collection": [
                            {"doi": "10.1101/2024.01.01.123456", "version": "2", "date": "2024-02-01", "published": "10.1000/final"},
                            {"doi": "10.1101/2024.01.01.123456", "version": "1", "date": "2024-01-01", "published": "NA"},
                        ]
                    },
                )
            ]
        )
        result = preprint_record("10.1101/2024.01.01.123456", "biorxiv", client=client)
        self.assertEqual([record["version"] for record in result["versions"]], ["1", "2"])
        self.assertEqual(result["latest_version"]["version"], "2")
        self.assertEqual(result["published_dois"], ["10.1000/final"])

    def test_pubchem_retains_identity_and_stereochemistry(self):
        properties = {
            "PropertyTable": {
                "Properties": [
                    {
                        "CID": 2244,
                        "Title": "Aspirin",
                        "MolecularFormula": "C9H8O4",
                        "SMILES": "CC(=O)OC1=CC=CC=C1C(=O)O",
                        "ConnectivitySMILES": "CC(=O)OC1=CC=CC=C1C(=O)O",
                        "InChIKey": "BSYNRYMUTXBXSQ-UHFFFAOYSA-N",
                    }
                ]
            }
        }
        synonyms = {"InformationList": {"Information": [{"CID": 2244, "Synonym": ["Aspirin", "Acetylsalicylic acid"]}]}}
        client = self.client([("/property/", properties), ("/cid/2244/synonyms/", synonyms)])
        result = pubchem_compound("aspirin", client=client)
        self.assertEqual(result["identity_checks"]["unique_cids"], [2244])
        self.assertTrue(result["identity_checks"]["stereochemistry_fields_retained"])
        self.assertEqual(result["synonyms"][1], "Acetylsalicylic acid")

    def test_clinical_trial_parser_retains_protocol_and_results_state(self):
        study = {
            "protocolSection": {
                "identificationModule": {"nctId": "NCT00000001", "briefTitle": "Trial", "officialTitle": "A Trial"},
                "designModule": {
                    "studyType": "INTERVENTIONAL",
                    "phases": ["PHASE2"],
                    "enrollmentInfo": {"count": 120, "type": "ACTUAL"},
                    "designInfo": {"allocation": "RANDOMIZED", "interventionModel": "PARALLEL"},
                },
                "statusModule": {"overallStatus": "COMPLETED"},
            },
            "hasResults": True,
            "resultsSection": {"participantFlowModule": {}},
        }
        client = self.client([("/api/v2/studies", {"studies": [study], "totalCount": 1})])
        result = clinical_trial_records("retina", client=client)
        self.assertEqual(result["studies"][0]["nct_id"], "NCT00000001")
        self.assertEqual(result["studies"][0]["enrollment"]["count"], 120)
        self.assertTrue(result["studies"][0]["has_results"])
        self.assertEqual(result["api_total_count"], 1)
        self.assertFalse(result["records_truncated"])
        self.assertEqual(result["local_post_filters_applied"], [])

    def test_clinical_trial_filters_paginate_and_reconcile_total(self):
        def study(nct_id):
            return {
                "protocolSection": {
                    "identificationModule": {"nctId": nct_id, "briefTitle": nct_id},
                    "designModule": {"studyType": "INTERVENTIONAL", "phases": ["PHASE2"]},
                    "statusModule": {"overallStatus": "COMPLETED"},
                },
                "hasResults": False,
            }

        class PagingTransport:
            def __init__(self):
                self.urls = []

            def __call__(self, url, _headers, _timeout):
                self.urls.append(url)
                payload = (
                    {"studies": [study("NCT00000002")], "totalCount": 2, "nextPageToken": "next-token"}
                    if "pageToken=" not in url
                    else {"studies": [study("NCT00000001")]}
                )
                return HTTPResponse(200, {}, json.dumps(payload).encode())

        transport = PagingTransport()
        client = PublicJSONClient(transport=transport, retries=0, sleeper=lambda _: None)
        result = clinical_trial_records(
            filters={
                "condition": "retinal degeneration",
                "overall_status": ["COMPLETED"],
                "phase": ["PHASE2", "PHASE3"],
                "enrollment_min": 10,
                "first_posted_end": "2025-12-31",
                "location_city": "Boston",
                "location_country": "United States",
                "location_recruiting_only": True,
                "investigator": "Jane Smith",
                "investigator_role": "official",
                "sponsor_name": "National Institutes of Health",
                "sponsor_scope": "any",
                "eligibility_keywords": ["confirmed diagnosis"],
            },
            page_size=1,
            max_records=10,
            client=client,
        )
        self.assertEqual(result["nct_ids"], ["NCT00000001", "NCT00000002"])
        self.assertEqual(result["api_total_count"], 2)
        self.assertEqual(len(result["provenance"]["requests"]), 2)
        self.assertFalse(result["records_truncated"])
        first_url = transport.urls[0]
        self.assertIn("query.cond=retinal+degeneration", first_url)
        self.assertIn("filter.overallStatus=COMPLETED", first_url)
        self.assertIn("SEARCH%5BLocation%5D", first_url)
        self.assertIn("LocationCountry", first_url)
        self.assertIn("OverallOfficialName", first_url)
        self.assertIn("CollaboratorName", first_url)
        self.assertIn("EligibilityCriteria", first_url)

    def test_clinical_trial_truncation_and_invalid_filters_are_explicit(self):
        study = {
            "protocolSection": {
                "identificationModule": {"nctId": "NCT00000001"},
                "designModule": {"studyType": "OBSERVATIONAL"},
                "statusModule": {"overallStatus": "COMPLETED"},
            }
        }
        client = self.client([("/api/v2/studies", {"studies": [study], "totalCount": 20, "nextPageToken": "more"})])
        result = clinical_trial_records("retina", page_size=1, max_records=1, client=client)
        self.assertTrue(result["records_truncated"])
        self.assertTrue(result["next_page_token_present"])
        with self.assertRaises(ValueError):
            clinical_trial_records(filters={"unknown": "value"}, client=client)
        with self.assertRaises(ValueError):
            clinical_trial_records(filters={"phase": ["PHASE9"]}, client=client)

    def test_rcsb_parser_validates_identifier_and_retains_quality_context(self):
        payload = {
            "rcsb_id": "4HHB",
            "struct": {"title": "Hemoglobin"},
            "exptl": [{"method": "X-RAY DIFFRACTION"}],
            "rcsb_entry_info": {"resolution_combined": [1.74]},
            "rcsb_accession_info": {"initial_release_date": "1984-07-17"},
            "rcsb_primary_citation": {"pdbx_database_id_DOI": "10.1000/example"},
            "rcsb_entry_container_identifiers": {"polymer_entity_ids": ["1", "2"]},
            "pdbx_database_status": {"status_code": "REL"},
        }
        client = self.client([("/rest/v1/core/entry/4HHB", payload)])
        result = rcsb_structure_records(["4hhb"], client=client)
        self.assertEqual(result["structures"][0]["resolution_combined"], [1.74])
        self.assertEqual(result["structures"][0]["experimental_methods"], ["X-RAY DIFFRACTION"])

    def test_rcsb_search_pages_and_reconciles_api_total(self):
        class SearchTransport:
            def __init__(self):
                self.payloads = []

            def __call__(self, _url, _headers, body, _timeout):
                request = json.loads(body)
                self.payloads.append(request)
                start = request["request_options"]["paginate"]["start"]
                page = (
                    [{"identifier": "4HHB", "score": 1.0}, {"identifier": "1TUP", "score": 0.9}]
                    if start == 0
                    else [{"identifier": "1CRN", "score": 0.8}]
                )
                return HTTPResponse(200, {}, json.dumps({"total_count": 3, "result_set": page}).encode())

        transport = SearchTransport()
        client = PublicJSONClient(post_transport=transport, retries=0, sleeper=lambda _: None)
        result = rcsb_structure_search(
            organism="Homo sapiens",
            experimental_method="X-RAY DIFFRACTION",
            max_resolution=2.5,
            max_records=3,
            client=client,
        )
        self.assertEqual([record["pdb_id"] for record in result["records"]], ["4HHB", "1TUP", "1CRN"])
        self.assertEqual(result["total_count"], 3)
        self.assertFalse(result["records_truncated"])
        self.assertEqual(len(transport.payloads), 2)
        self.assertEqual(transport.payloads[1]["request_options"]["paginate"]["start"], 2)

    def test_rcsb_search_treats_first_page_204_as_explicit_zero_results(self):
        class EmptySearchTransport:
            def __call__(self, _url, _headers, _body, _timeout):
                return HTTPResponse(204, {}, b"")

        client = PublicJSONClient(post_transport=EmptySearchTransport(), retries=0, sleeper=lambda _: None)
        result = rcsb_structure_search(text="no-such-structure-query", client=client)
        self.assertEqual(result["total_count"], 0)
        self.assertEqual(result["returned_count"], 0)
        self.assertEqual(result["records"], [])
        self.assertFalse(result["records_truncated"])
        self.assertEqual(result["provenance"]["requests"][0]["request"]["status_code"], 204)

    def test_rcsb_polymer_entities_preserve_sequence_and_not_found(self):
        entry = {"rcsb_entry_container_identifiers": {"polymer_entity_ids": ["1", "2"]}}
        entity = {
            "rcsb_id": "4HHB_1",
            "rcsb_polymer_entity": {"pdbx_description": "Hemoglobin subunit alpha"},
            "rcsb_polymer_entity_container_identifiers": {"entry_id": "4HHB", "entity_id": "1", "uniprot_ids": ["P69905"]},
            "entity_poly": {"rcsb_entity_polymer_type": "Protein", "rcsb_sample_sequence_length": 141, "pdbx_seq_one_letter_code_can": "VLSPADKT"},
            "rcsb_entity_source_organism": [{"scientific_name": "Homo sapiens", "ncbi_taxonomy_id": 9606}],
        }
        client = self.client(
            [
                ("/entry/4HHB", entry),
                ("/polymer_entity/4HHB/1", entity),
                ("/polymer_entity/4HHB/2", HTTPResponse(404, {}, b"{}")),
            ]
        )
        result = rcsb_polymer_entity_records("4hhb", include_sequences=True, client=client)
        self.assertEqual(result["entry_polymer_entity_count"], 2)
        self.assertEqual(result["entities"][0]["sequence"], "VLSPADKT")
        self.assertEqual(result["not_found"], ["2"])

    def test_rcsb_ligand_chain_retains_component_identity_and_missing_state(self):
        entry = {"rcsb_entry_container_identifiers": {"non_polymer_entity_ids": ["1", "2"]}}
        entity = {
            "rcsb_nonpolymer_entity_container_identifiers": {"entity_id": "1", "nonpolymer_comp_id": "HEM", "auth_asym_ids": ["A"]},
            "rcsb_nonpolymer_entity": {"pdbx_description": "Heme", "pdbx_number_of_molecules": 1},
        }
        component = {
            "chem_comp": {"id": "HEM", "name": "PROTOPORPHYRIN IX CONTAINING FE", "formula": "C34 H32 Fe N4 O4", "pdbx_formal_charge": 0},
            "rcsb_chem_comp_descriptor": {"InChIKey": "KABFMIBPWCXCRK-RGGAHWMASA-L", "SMILES_stereo": "[Fe]"},
        }
        client = self.client(
            [
                ("/entry/4HHB", entry),
                ("/nonpolymer_entity/4HHB/1", entity),
                ("/nonpolymer_entity/4HHB/2", HTTPResponse(404, {}, b"{}")),
                ("/chemcomp/HEM", component),
            ]
        )
        result = rcsb_ligand_records("4HHB", client=client)
        self.assertEqual(result["ligands"][0]["chemical_component"]["comp_id"], "HEM")
        self.assertEqual(result["not_found_entity_ids"], ["2"])
        self.assertFalse(result["records_truncated"])

    def test_alphafold_records_preserve_model_confidence_versions_and_absence(self):
        model = {
            "modelEntityId": "AF-P04637-F1",
            "entryId": "AF-P04637-F1",
            "providerId": "GDM",
            "toolUsed": "AlphaFold Monomer v2.0 pipeline",
            "uniprotAccession": "P04637",
            "uniprotId": "P53_HUMAN",
            "uniprotDescription": "Cellular tumor antigen p53",
            "gene": "TP53",
            "organismScientificName": "Homo sapiens",
            "taxId": 9606,
            "sequence": "MEEPQ",
            "uniprotStart": 1,
            "uniprotEnd": 5,
            "globalMetricValue": 72.5,
            "fractionPlddtVeryLow": 0.1,
            "fractionPlddtLow": 0.2,
            "fractionPlddtConfident": 0.3,
            "fractionPlddtVeryHigh": 0.4,
            "latestVersion": 6,
            "allVersions": [1, 2, 3, 4, 5, 6],
            "modelCreatedDate": "2025-08-01",
            "cifUrl": "https://alphafold.ebi.ac.uk/files/AF-P04637-F1-model_v6.cif",
            "paeDocUrl": "https://alphafold.ebi.ac.uk/files/AF-P04637-F1-predicted_aligned_error_v6.json",
        }
        client = self.client(
            [
                ("/api/prediction/P04637", [model]),
                ("/api/prediction/Q9Y6K9", HTTPResponse(404, {}, b"{}")),
            ]
        )
        result = alphafold_structure_records(["p04637", "Q9Y6K9"], include_sequence=True, client=client)
        self.assertEqual(result["requested_count"], 2)
        self.assertEqual(result["covered_count"], 1)
        self.assertEqual(result["not_covered_count"], 1)
        self.assertEqual(result["records"][0]["models"][0]["sequence"], "MEEPQ")
        self.assertEqual(result["records"][0]["models"][0]["global_plddt"], 72.5)
        self.assertEqual(result["records"][0]["models"][0]["fraction_plddt_sum"], 1.0)
        self.assertFalse(result["records"][1]["has_model"])
        self.assertTrue(result["provenance"]["requests"][1]["not_found"])

    def test_alphafold_blocks_invalid_accessions_and_confidence(self):
        with self.assertRaises(ValueError):
            alphafold_structure_records(["TP53"], client=self.client([]))
        bad = {"uniprotAccession": "P04637", "globalMetricValue": 101}
        with self.assertRaisesRegex(PublicDatabaseError, "pLDDT range"):
            alphafold_structure_records(
                ["P04637"],
                client=self.client([("/api/prediction/P04637", [bad])]),
            )

    def test_iupred2a_preserves_profile_and_calls_transparent_threshold_spans(self):
        client = self.client(
            [
                (
                    "/iupred2a/long/P04637.json",
                    {"sequence": "MEEPQ", "type": "long", "iupred2": [0.1, 0.6, 0.8, 0.4, 0.7]},
                ),
                ("/iupred2a/long/Q9Y6K9.json", HTTPResponse(404, {}, b"{}")),
            ]
        )
        result = iupred2a_disorder_prediction(
            ["p04637", "Q9Y6K9"], score_threshold=0.5, minimum_span_length=2, client=client
        )
        self.assertEqual(result["found_count"], 1)
        self.assertEqual(result["not_found_count"], 1)
        self.assertEqual(result["records"][0]["score_count"], 5)
        self.assertEqual(result["records"][0]["threshold_spans"], [{"start": 2, "end": 3, "length": 2, "mean_score": 0.7}])
        self.assertFalse(result["records"][1]["found"])

    def test_iupred2a_blocks_incoherent_profiles_and_unsupported_modes(self):
        with self.assertRaisesRegex(ValueError, "prediction_type"):
            iupred2a_disorder_prediction(["P04637"], prediction_type="anchor", client=self.client([]))
        with self.assertRaisesRegex(PublicDatabaseError, "reconcile"):
            iupred2a_disorder_prediction(
                ["P04637"], client=self.client([("/iupred2a/long/P04637.json", {"sequence": "MEEPQ", "type": "long", "iupred2": [0.2]})])
            )

    def test_post_transport_rejects_unapproved_hosts_and_oversized_payloads(self):
        client = PublicJSONClient(post_transport=lambda *_: HTTPResponse(200, {}, b"{}"), retries=0)
        with self.assertRaises(ValueError):
            client.post_with_metadata("https://example.com", "/query", {})
        with self.assertRaises(ValueError):
            client.post_with_metadata("https://search.rcsb.org", "/rcsbsearch/v2/query", {"value": "x" * (1024 * 1024)})

    def test_transport_blocks_unapproved_hosts_and_invalid_responses(self):
        client = self.client([])
        with self.assertRaises(ValueError):
            client.get("https://example.com", "/data")
        invalid = PublicJSONClient(
            transport=lambda *_: HTTPResponse(200, {}, b"not-json"),
            retries=0,
            sleeper=lambda _: None,
        )
        with self.assertRaises(PublicDatabaseError):
            invalid.get("https://api.crossref.org", "/v1/works")
        failed = PublicJSONClient(
            transport=lambda *_: HTTPResponse(503, {}, b"{}"),
            retries=0,
            sleeper=lambda _: None,
        )
        with self.assertRaisesRegex(PublicDatabaseError, "HTTP 503"):
            failed.get("https://api.crossref.org", "/v1/works")

    def test_ncbi_gene_orthologs_uses_a_fixed_path_and_preserves_target_records(self):
        client = self.client([("/datasets/v2/gene/id/7157/orthologs", {"reports": [
            {"gene": {"gene_id": "7157", "symbol": "TP53", "tax_id": "9606", "taxname": "Homo sapiens", "ensembl_gene_ids": ["ENSG00000141510"]}},
            {"gene": {"gene_id": "22059", "symbol": "Trp53", "tax_id": "10090", "taxname": "Mus musculus", "type": "PROTEIN_CODING", "ensembl_gene_ids": ["ENSMUSG00000059552"]}},
            {"gene": {"gene_id": "999", "symbol": "Other", "tax_id": "10116"}},
        ]})])
        result = ncbi_gene_orthologs("7157", 10090, client=client)
        self.assertEqual(result["source"]["symbol"], "TP53")
        self.assertEqual(result["orthologs"], [{"gene_id": "22059", "symbol": "Trp53", "tax_id": "10090", "taxname": "Mus musculus", "ensembl_gene_ids": ["ENSMUSG00000059552"], "type": "PROTEIN_CODING"}])
        self.assertIn("api.ncbi.nlm.nih.gov/datasets/v2/gene/id/7157/orthologs", client._transport.urls[0])
        with self.assertRaises(ValueError):
            ncbi_gene_orthologs("TP53", 10090, client=client)

    def test_ncbi_datasets_optional_key_is_header_only_and_never_in_provenance(self):
        observed = {}

        def transport(url, headers, _timeout):
            observed["url"] = url
            observed["headers"] = dict(headers)
            payload = {
                "reports": [
                    {
                        "gene": {
                            "gene_id": "7157",
                            "symbol": "TP53",
                            "tax_id": "9606",
                            "taxname": "Homo sapiens",
                        }
                    }
                ]
            }
            return HTTPResponse(200, {"Content-Type": "application/json"}, json.dumps(payload).encode())

        client = PublicJSONClient(transport=transport, retries=0, sleeper=lambda _: None)
        with patch(
            "biomed_workbench.services.public_databases.optional_credential",
            return_value="test-secret-that-must-not-leak",
        ):
            result = ncbi_gene_orthologs("7157", 10090, client=client)

        self.assertEqual(observed["headers"]["api-key"], "test-secret-that-must-not-leak")
        self.assertNotIn("test-secret-that-must-not-leak", observed["url"])
        self.assertTrue(result["provenance"]["api_key_used"])
        self.assertNotIn("test-secret-that-must-not-leak", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
