#!/usr/bin/env python


'''
  Loads individual from rare_variants CSV file produced by Vincent.

  Get genes with damaging variants (usually hom / het / rare) from individual
  and query them against pubmed using pubmedPython
'''

from pprint import pprint
import os
import json
import pymongo
import sys
import re
import itertools
from urllib2 import HTTPError, URLError
import pysam
import csv
from collections import defaultdict, Counter
import rest as annotation
import vcf
from phenotips_python_client import PhenotipsClient
from optparse import OptionParser
import mygene
import lookups
import orm
import subprocess


def find_item(obj, key):
    if key in obj:
        return obj[key]
    if isinstance(obj, dict):
        for k in obj:
            if isinstance(obj[k], dict):
                item = find_item(obj[k], key)
                if item is not None:
                    return item
            elif isinstance(obj[k], list):
                for i in obj[k]:
                    if isinstance(i, str):
                        continue
                    item = find_item(i, key)
                    if item is not None:
                        return item
    elif isinstance(obj, list):
        for k in obj:
            if isinstance(k, dict):
                item = find_item(k, key)
                if item is not None:
                    return item
            elif isinstance(k, list):
                for i in k:
                    if isinstance(i, str):
                        continue
                    item = find_item(i, key)
                    if item is not None:
                        return item

def load_patient(filename,auth,hpo='HP:0000001'): 
    # Some constant
    RETNET  = json.load(open('/home/rmhanpo/uclex_browser/retnet.json', 'r'))
    #HEADER = ['HUGO', 'HPO', 'consequence', 'ref(pubmedID)', 'description', 'OMIM', 'allele_freq', 'ExAC_freq', 'variant_id', 'p_change']
    # get db
    client = pymongo.MongoClient()
    hpo_db = client['hpo']
    db = client['uclex']
    patient_db = client['patients']
    patient_id=os.path.basename(filename.replace('.csv','')) 
    parent_dir=os.path.basename(os.path.abspath(os.path.join(filename, os.pardir)))
    # Add patient to phenotips if it does not already exist
    pheno=PhenotipsClient()
    patient={u'features':[], 'clinicalStatus': {u'clinicalStatus': u'affected'}, u'ethnicity': {u'maternal_ethnicity': [], u'paternal_ethnicity': []}, u'family_history': {}, u'disorders': [], u'life_status': u'alive', u'reporter': u'', u'genes': [], u'prenatal_perinatal_phenotype': {u'prenatal_phenotype': [], u'negative_prenatal_phenotype': []}, u'prenatal_perinatal_history': {u'twinNumber': u''}, u'sex': u'U', u'solved': {u'status': u'unsolved'}}
    eid=patient_id
    p=pheno.get_patient(auth=auth,eid=eid)
    print p
    if p is None:
        print 'MISSING', eid
        patient['features']=[ {'id':h,'type':'phenotype','observed':'yes'} for h in hpo.strip().split(',')]
        patient['external_id']=eid
        print 'CREATING', eid
        print pheno.create_patient(auth,patient)
    if not patient_db.patients.find_one({'external_id':eid}):
        # update database
        p=pheno.get_patient(eid=eid,auth=auth)
        print 'UPDATE'
        print patient_db.patients.update({'external_id':eid},{'$set':p},w=0,upsert=True)
    patient_hpo_terms=lookups.get_patient_hpo(hpo_db, patient_db, patient_id, ancestors=False)
    patient_hpo_terms = dict([(hpo['id'][0],{'id':hpo['id'][0],'name':hpo['name'][0], 'is_a':hpo.get('is_a',[])}) for hpo in patient_hpo_terms])
    patient_hpo_ids=patient_hpo_terms.keys()
    # get hpo terms from patient
    print 'processing rare variants of %s' % patient_id
    print 'patient hpo terms', patient_hpo_terms 
    variants_reader=csv.DictReader(open(filename))
    #for var in ['homozygous_variants', 'compound_hets', 'rare_variants']:
    VARIANTS=[]
    for var in variants_reader:
        # look up variant on myvariant
        chrom, pos, ref, alt, = var['signature'].split('_')
        #for k in var.keys(): print k, ':', var[k]
        #break
        variant=vcf.vcf_query(chrom, pos, ref, alt, individual=patient_id, limit=100)
        if variant is None:
            sys.stderr.write( '\033[01;31m' + var['signature'] + ' not found!' + '\033[m' + '\n' )
            with open("notfound.txt", "a") as myfile: myfile.write(var['signature'])
            continue
        print var['signature'], '==>', variant['POS'], variant['REF'], variant['ALT']
        #variant['site_quality'] = variant['QUAL']
        #variant['filter'] = variant['FILTER']
        #pprint(variant)
        #variant['vep']=vep_anno(str(chrom), str(pos), ref, alt,)
        #variant['my_variant']=mv.getvariant(variant['hgvs'],fields='all')
        #variant['rvs']=rvs_anno(chrom,pos,ref,alt)
        variant['exac']=annotation.exac_anno(variant['variant_id'])
        #print(variant['exac'])
        for k in var: variant[k]=var[k]
        #print vep_anno(chrom, pos, ref, alt)
        VAR=dict()
        if patient_id in variant['hom_samples']: VAR['variant_type']='rare_homozygous'
        elif patient_id in variant['het_samples']: VAR['variant_type']='rare_het'
        else:
            print variant['het_samples']
            print variant['hom_samples']
            print patient_id, 'not in hom or het samples'
            VAR['variant_type']='rare_het'
            #raise 'hell'
        VAR['variant_id']=variant['variant_id']
        VAR['allele_freq']=[ variant['allele_freq'], str(variant['allele_count'])+'/'+str(variant['allele_num']), variant['MISS_COUNT']]
        print(VAR['allele_freq'])
        #rvs=[impact for impact in variant['rvs']['impact'] if impact['alt']==alt]
        #if len(rvs)==1:
        VAR['HUGO']=re.sub('\(.*\)','',variant['HUGO'])
        VAR['HUGO']=re.sub(',.*','',VAR['HUGO'])
        VAR['ExAC_freq']=variant['exac']
        VAR['Gene']=re.sub('\(.*\)','',variant['Gene'])
        if VAR['HUGO']=='NA':
            gene_id=VAR['Gene'].split(',')[0]
            g=db.genes.find_one({'gene_id':gene_id})
            if not g and 'vep_annotations' in variant['exac']:
                VAR['HUGO']=variant['exac']['vep_annotations'][0]['SYMBOL']
            else:
                #g=mg.query(gene_id, scopes='symbol', fields='ensembl.gene', species='human')
                g=annotation.ensembl_xrefs(gene_id)
                if 'error' in g:
                    # unnamed gene
                    VAR['HUGO']=''
                else:
                    print gene_id, g
                    VAR['HUGO']=find_item(g,'display_id')
        # get annotation from CSV file
        if variant['splicing']=='FALSE':
            if not variant['AAChange']: variant['AAChange']=re.compile('.*\((.*)\)').search(variant['Gene']).group(1)
            VAR['p_change']=dict(zip(['gene_id','transcript_id','exon','hgvs_c','hgvs_p'],variant['AAChange'].split(':')))
            if 'hgvs_p' in VAR['p_change']: VAR['p_change']['hgvs_p']=re.sub(',.*','',VAR['p_change']['hgvs_p'])
        else:
            VAR['p_change']={}
        VAR['consequence']=variant['ExonicFunc']
        VAR['filter']=variant['FILTER']
        VAR['OMIM']=variant.get('Omim','').split(';')[0]
        VAR['lof']=bool(variant['lof'])
        VAR['description']=variant['Description']
        if VAR['lof']:
            print 'lof'
            print VAR['HUGO']
            g=db.genes.find_one({'gene_name_upper':VAR['HUGO'].upper()})
            if g:
                gene_id=g['gene_id']
                print gene_id
            else:
                mg=mygene.MyGeneInfo()
                g=mg.query(VAR['HUGO'], scopes='symbol', fields='ensembl.gene', species='human')
                print g
                if g and 'hits' in g and len(g['hits'])>0 and 'ensembl' in g['hits'][0]:
                    print g
                    # {u'hits': [{u'_id': u'643669', u'ensembl': [{u'gene': u'ENSG00000262484'}, {u'gene': u'ENSG00000283099'}]}], u'total': 1, u'max_score': 443.8707, u'took': 2}
                    gene_id=find_item(g,'gene')
                    #gene_id=[x for _, x, in g['hits'][0]['ensembl'][0].iteritems()]
                    print gene_id
                    #raise 'hell'
                else:
                    e=annotation.ensembl_region('{}:{}-{}'.format(chrom,pos,pos))
                    gene_id=e[0]['gene_id']
                    print gene_id
            lof=db.lof.find_one({'gene_id':gene_id})
            if lof:
                lof['patient_ids'][patient_id]=list(set(lof['patient_ids'].get(patient_id,[])+[VAR['variant_id']]))
                print db.lof.update({'gene_id':gene_id}, {'$set':{'patient_ids':lof['patient_ids']}})
            else:
                print db.lof.insert({'gene_id':gene_id,'patient_ids':{patient_id:[VAR['variant_id']]}})
        #hpo_terms=hpo_db.gene_hpo.find_one({'gene_name':VAR['HUGO']},{'hpo_terms':1,'_id':1})
        #gene_hpo_ids=hpo_db.gene_hpo.find_one({'gene_name':'ABCA4'},{'hpo_terms':1,'_id':0}).get('hpo_terms',[])
        #VAR['HUGO']='ABCA4'
        gene_hpo_terms=lookups.get_gene_hpo(hpo_db,VAR['HUGO'],False)
        gene_hpo_terms = dict([(hpo['id'][0],{'id':hpo['id'][0],'name':hpo['name'][0], 'is_a':hpo.get('is_a',[])}) for hpo in gene_hpo_terms])
        gene_hpo_ids=gene_hpo_terms.keys()
        #lookups.get_gene_hpo(hpo_db,gene_name,dot=False)
        #print 'gene', gene_hpo_ids
        #print 'patient', patient_hpo_ids
        common_hpo_ids=list(set(gene_hpo_ids) & set(patient_hpo_ids))
        # simplify hpo terms
        common_hpo_ids=lookups.hpo_minimum_set(hpo_db, common_hpo_ids)
        common_hpo_ids=[{'hpo_id':k,'hpo_term':patient_hpo_terms[k]['name']} for k in common_hpo_ids]
        print VAR['HUGO'],common_hpo_ids
        VAR['HPO']=common_hpo_ids
        VARIANTS.append(VAR)
    # determine count per gene
    gene_counter=Counter([var['HUGO'] for var in VARIANTS])
    for var in VARIANTS: var['gene_count']=gene_counter[var['HUGO']]
    print('gene_counter', gene_counter)
    print('rare_variants',len(VARIANTS))
    print(db.patients.update({'external_id':patient_id}, {'$set':{'rare_variants':VARIANTS}}, upsert=True))
    print(db.patients.update({'external_id':patient_id}, {'$set':{'rare_variants_count':len(VARIANTS)}}, upsert=True))
    COMPOUND_HETS=[var for var in VARIANTS if var['gene_count']>1]
    print('compound_hets',len(COMPOUND_HETS))
    print(db.patients.update({'external_id':patient_id}, {'$set':{'compound_hets':COMPOUND_HETS}}, upsert=True)) 
    print(db.patients.update({'external_id':patient_id}, {'$set':{'compound_hets_count':len(COMPOUND_HETS)}}, upsert=True)) 
    HOMOZYGOUS_VARIANTS=[var for var in VARIANTS if var['variant_type']=='rare_homozygous']
    print('rare_homozygous',len(HOMOZYGOUS_VARIANTS))
    print(db.patients.update({'external_id':patient_id}, {'$set':{'homozygous_variants':HOMOZYGOUS_VARIANTS}}, upsert=True))
    print(db.patients.update({'external_id':patient_id}, {'$set':{'homozygous_variants_count':len(HOMOZYGOUS_VARIANTS)}}, upsert=True))


def load_patient2(individual,auth,AC=5): 
    # Some constant
    RETNET  = json.load(open('/home/rmhanpo/uclex_browser/retnet.json', 'r'))
    #HEADER = ['HUGO', 'HPO', 'consequence', 'ref(pubmedID)', 'description', 'OMIM', 'allele_freq', 'ExAC_freq', 'variant_id', 'p_change']
    # get db
    client = pymongo.MongoClient()
    hpo_db = client['hpo']
    db = client['uclex']
    patient_db = client['patients']
    patient_id=individual
    # Add patient to phenotips if it does not already exist
    pheno=PhenotipsClient()
    patient={u'features':[], 'clinicalStatus': {u'clinicalStatus': u'affected'}, u'ethnicity': {u'maternal_ethnicity': [], u'paternal_ethnicity': []}, u'family_history': {}, u'disorders': [], u'life_status': u'alive', u'reporter': u'', u'genes': [], u'prenatal_perinatal_phenotype': {u'prenatal_phenotype': [], u'negative_prenatal_phenotype': []}, u'prenatal_perinatal_history': {u'twinNumber': u''}, u'sex': u'U', u'solved': {u'status': u'unsolved'}}
    eid=patient_id
    p=pheno.get_patient(auth=auth,eid=eid)
    print p
    if p is None:
        print 'MISSING', eid
        patient['features']=[ {'id':h,'type':'phenotype','observed':'yes'} for h in hpo.strip().split(',')]
        patient['external_id']=eid
        print 'CREATING', eid
        print pheno.create_patient(auth,patient)
    if not patient_db.patients.find_one({'external_id':eid}):
        # update database
        p=pheno.get_patient(eid=eid,auth=auth)
        print 'UPDATE'
        print patient_db.patients.update({'external_id':eid},{'$set':p},w=0,upsert=True)
    patient_hpo_terms=lookups.get_patient_hpo(hpo_db, patient_db, patient_id, ancestors=False)
    patient_hpo_terms = dict([(hpo['id'][0],{'id':hpo['id'][0],'name':hpo['name'][0], 'is_a':hpo.get('is_a',[])}) for hpo in patient_hpo_terms])
    patient_hpo_ids=patient_hpo_terms.keys()
    # get hpo terms from patient
    print 'processing rare variants of %s' % patient_id
    print 'patient hpo terms', patient_hpo_terms 
    cmd="bgt view -s,"+individual+" -s 'name!=\""+individual+"\"' -f 'AC1>0&&AC2<%s' "%str(AC)+ "-G /slms/gee/research/vyplab/UCLex/mainset_July2016/bgt/mainset_July2016.bgt" 
    print(cmd)
    proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,shell=True)
    VARIANTS=[]
    for l in iter(proc.stdout.readline,''):
        l=l.strip()
        print(l)
        if len(l)<5: continue
        if l.startswith('##'): continue
        if l.startswith('#'):
            headers=l.split('\t')
            continue
        d=dict(zip(headers,l.split('\t')))
        d.update(dict([x.split('=') for x in d['INFO'].split(';')]))
        del d['INFO']
        if ',' in d['ALT']: d['ALT']=d['ALT'].split(',')[0]
        d['variant_id']='-'.join([d['#CHROM'],d['POS'],d['REF'],d['ALT']])
        try:
            var=orm.Variant(variant_id=d['variant_id'],db=db)
            print(var.HUGO)
            print(var.consequence)
            print(var.filter)
            print(var.p_change)
            print(var.description)
            print(var.ExAC_freq)
            print(var.allele_freq)
            if individual in var.hom_samples: var.variant_type='rare_homozygous'
            else: var.variant_type=''
            VARIANTS.append(var)
        except Exception, e:
            print('ERROR:')
            print(e)
            print(d)
            break
    #return Response(stream_with_context(generate()),mimetype='application/json')
    # determine count per gene
    gene_counter=Counter([var.HUGO for var in VARIANTS])
    for var in VARIANTS: var.gene_count=gene_counter[var.HUGO]
    print('gene_counter', gene_counter)
    print('rare_variants',len(VARIANTS))
    COMPOUND_HETS=[var.__dict__ for var in VARIANTS if var.gene_count>1]
    print('compound_hets',len(COMPOUND_HETS))
    print(db.patients.update({'external_id':patient_id}, {'$set':{'compound_hets':COMPOUND_HETS}}, upsert=True)) 
    print(db.patients.update({'external_id':patient_id}, {'$set':{'compound_hets_count':len(COMPOUND_HETS)}}, upsert=True)) 
    HOMOZYGOUS_VARIANTS=[var.__dict__ for var in VARIANTS if var.variant_type=='rare_homozygous']
    print('rare_homozygous',len(HOMOZYGOUS_VARIANTS))
    print(db.patients.update({'external_id':patient_id}, {'$set':{'homozygous_variants':HOMOZYGOUS_VARIANTS}}, upsert=True))
    print(db.patients.update({'external_id':patient_id}, {'$set':{'homozygous_variants_count':len(HOMOZYGOUS_VARIANTS)}}, upsert=True))
    VARIANTS=[var.__dict__ for var in VARIANTS]
    print(db.patients.update({'external_id':patient_id}, {'$set':{'rare_variants':VARIANTS}}, upsert=True))
    print(db.patients.update({'external_id':patient_id}, {'$set':{'rare_variants_count':len(VARIANTS)}}, upsert=True))





if '__main__'==__name__:
    # get patients
    # '/slms/UGI/vm_exports/vyp/phenotips/UKIRDC/homozygous_variants/IRDC_batch4_LON_2043_GC18419.csv'
    # '/slms/UGI/vm_exports/vyp/phenotips/UKIRDC/compound_hets/IRDC_batch4_LON_2043_GC18419.csv'
    # '/slms/UGI/vm_exports/vyp/phenotips/UKIRDC/rare_variants/IRDC_batch4_LON_2043_GC18419.csv'
    #filename='/slms/UGI/vm_exports/vyp/phenotips/UKIRDC/rare_variants/%s.csv' % this_patient
    ###############################
    # parse options
    ###############################
    usage = "usage: %prog [options] arg1 arg2"
    parser = OptionParser(usage=usage)
    parser.add_option("--filename", dest="filename", help="patient csv file")
    parser.add_option("--hpo", default='HP:0000001', dest="hpo", help="hpo term")
    parser.add_option("--auth", dest="auth", help="login")
    (options, args) = parser.parse_args()
    filename=options.filename
    auth=options.auth
    hpo=options.hpo
    load_patient(filename,auth,hpo)


