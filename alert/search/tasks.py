import socket
import sys
execfile('/etc/courtlistener')
sys.path.append(INSTALL_ROOT)

from alert import settings
from django.core.management import setup_environ
setup_environ(settings)

from alert.lib import sunburnt
from alert.search.models import Citation
from alert.search.models import Document
from alert.search.search_indexes import InvalidDocumentError
from alert.search.search_indexes import SearchDocument
from celery.decorators import task


@task
def add_or_update_doc_object(doc):
    """Adds a document object to the solr index.

    This function is for use with the update_index command. It's slightly
    different than the commands below because it expects a Django object,
    rather than a primary key. This rejects the standard Celery advice about
    not passing objects around, but thread safety shouldn't be an issue since
    this is only used by the update_index command, and we want to query and
    build the SearchDocument objects in the task, not in its caller.
    """
    si = sunburnt.SolrInterface(settings.SOLR_URL, mode='w')
    try:
        search_doc = SearchDocument(doc)
        si.add(search_doc)
    except AttributeError:
        print "AttributeError trying to add doc.pk: %s" % doc.pk
    except InvalidDocumentError:
        print "Unable to parse document %s" % doc.pk
    except socket.error, exc:
        add_or_update_doc_object.retry(exc=exc, countdown=120)

@task
def delete_docs(docs):
    si = sunburnt.SolrInterface(settings.SOLR_URL, mode='w')
    si.delete(list(docs))
    si.commit()

@task
def add_or_update_docs(docs):
    si = sunburnt.SolrInterface(settings.SOLR_URL, mode='w')
    for doc in docs:
        doc = Document.objects.get(pk=doc)
        search_doc = SearchDocument(doc)
        si.add(search_doc)
        si.commit()

@task
def delete_doc(document_id):
    """Deletes the document from the index.

    Called by Document delete function and from models.py when an item is deleted.

    Note that putting a line like...

      if document_id is not None:

    ...will mean that models.py deletions won't work. We've had a bug with that in
    the past, so exercise caution when tweaking this function.
    """
    si = sunburnt.SolrInterface(settings.SOLR_URL, mode='w')
    si.delete(document_id)
    si.commit()

@task
def add_or_update_doc(document_id):
    """Updates the document in the index. Called by Document save function.
    """
    si = sunburnt.SolrInterface(settings.SOLR_URL, mode='w')
    doc = Document.objects.get(pk=document_id)
    search_doc = SearchDocument(doc)
    si.add(search_doc)
    si.commit()

@task
def update_cite(citation_id):
    """If a citation and a document are both updated simultaneously, we will
    needlessly update the index twice. No easy way around it.
    """
    si = sunburnt.SolrInterface(settings.SOLR_URL, mode='w')
    cite = Citation.objects.get(pk=citation_id)
    for doc in cite.document_set.all():
        search_doc = SearchDocument(doc)
        si.add(search_doc)
    si.commit()
