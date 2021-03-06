import rest
import vcf
import json
from operator import itemgetter
import pprint
import requests


# Note that this is the current as of v77 with 2 included for backwards compatibility (VEP <= 75)
csq_order = ["transcript_ablation",
"splice_donor_variant",
"splice_acceptor_variant",
"stop_gained",
"frameshift_variant",
"stop_lost",
"initiator_codon_variant",
"transcript_amplification",
"inframe_insertion",
"inframe_deletion",
"missense_variant",
"splice_region_variant",
"incomplete_terminal_codon_variant",
"stop_retained_variant",
"synonymous_variant",
"coding_sequence_variant",
"mature_miRNA_variant",
"5_prime_UTR_variant",
"3_prime_UTR_variant",
"non_coding_transcript_exon_variant",
"non_coding_exon_variant",  # deprecated
"intron_variant",
"NMD_transcript_variant",
"non_coding_transcript_variant",
"nc_transcript_variant",  # deprecated
"upstream_gene_variant",
"downstream_gene_variant",
"TFBS_ablation",
"TFBS_amplification",
"TF_binding_site_variant",
"regulatory_region_ablation",
"regulatory_region_amplification",
"regulatory_region_variant",
"feature_elongation",
"feature_truncation",
"intergenic_variant",
"start_lost",
'protein_altering_variant',
""]
csq_order_dict = dict(zip(csq_order, range(len(csq_order))))
rev_csq_order_dict = dict(zip(range(len(csq_order)), csq_order))

def compare_two_consequences(csq1, csq2):
    if csq_order_dict[worst_csq_from_csq(csq1)] < csq_order_dict[worst_csq_from_csq(csq2)]:
        return -1
    elif csq_order_dict[worst_csq_from_csq(csq1)] == csq_order_dict[worst_csq_from_csq(csq2)]:
        return 0
    return 1

def get_protein_hgvs(csq):
    """
    Takes consequence dictionary, returns proper variant formatting for synonymous variants
    """
    if '%3D' in csq['HGVSp']:
        try:
            amino_acids = ''.join([protein_letters_1to3[x] for x in csq['Amino_acids']])
            return "p." + amino_acids + csq['Protein_position'] + amino_acids
        except Exception, e:
            print 'Could not create HGVS for: %s' % csq
    return csq['HGVSp'].split(':')[-1]


def worst_csq_index(csq_list):
    """
    Input list of consequences (e.g. ['frameshift_variant', 'missense_variant'])
    Return index of the worst annotation (In this case, index of 'frameshift_variant', so 4)
    Works well with csqs = 'non_coding_exon_variant&nc_transcript_variant' by worst_csq_index(csqs.split('&'))
    :param annnotation:
    :return most_severe_consequence_index:
    """
    return min([csq_order_dict[ann] for ann in csq_list])


def worst_csq_from_list(csq_list):
    """
    Input list of consequences (e.g. ['frameshift_variant', 'missense_variant'])
    Return the worst annotation (In this case, 'frameshift_variant')
    Works well with csqs = 'non_coding_exon_variant&nc_transcript_variant' by worst_csq_from_list(csqs.split('&'))
    :param annnotation:
    :return most_severe_consequence:
    """
    return rev_csq_order_dict[worst_csq_index(csq_list)]

def worst_csq_from_csq(csq):
    """
    Input possibly &-filled csq string (e.g. 'non_coding_exon_variant&nc_transcript_variant')
    Return the worst annotation (In this case, 'non_coding_exon_variant')
    :param consequence:
    :return most_severe_consequence:
    """
    return rev_csq_order_dict[worst_csq_index(csq.split('&'))]


def order_vep_by_csq(annotation_list):
    print('ANNOTATION LIST',annotation_list)
    output = sorted(annotation_list, cmp=lambda x, y: compare_two_consequences(x, y), key=itemgetter('consequence_terms'))
    for ann in output:
        ann['major_consequence'] = worst_csq_from_csq(ann['consequence_terms'])
    return output



def compare_two_consequences(csq1, csq2):
    if csq_order_dict[worst_csq_from_csq(csq1)] < csq_order_dict[worst_csq_from_csq(csq2)]:
        return -1
    elif csq_order_dict[worst_csq_from_csq(csq1)] == csq_order_dict[worst_csq_from_csq(csq2)]:
        return 0
    return 1

def get_variants_by_rsid(db, rsid):
    if not rsid.startswith('rs'):
        return None
    try:
        int(rsid.lstrip('rs'))
    except Exception, e:
        return None
    variants = list([Variant(data=v) for v in db.variants.find({'rsid': rsid}, fields={'_id': False})])
    #add_consequence_to_variants(variants)
    return variants


class Variant(object):
    def __init__(self, variant_id=None, db=None,data=None):
        if variant_id is None: variant_id=data['variant_id']
        self.variant_id=str(variant_id).strip().replace('_','-')
        self.chrom, self.pos, self.ref, self.alt = variant_id.split('-')
        q=vcf.vcf_query(variant_str=self.variant_id,)
        if q is None: raise Exception('NOT IN VCF',self.variant_id)
        self.__dict__.update(q)
        if data: self.__dict__.update(data)
        if db:
            Variant.db=db
            data=Variant.db.variants.find_one({'variant_id':self.variant_id},fields={'_id':False})
            if not data:
                print('NOT IN DB', self.variant_id, 'WILL INSERT')
                self.save()
                #self.xpos = get_xpos(self.chrom, self.pos)
            else:
                self.__dict__.update(data)
    def __getattribute__(self, key):
        "Emulate type_getattro() in Objects/typeobject.c"
        v = object.__getattribute__(self, key)
        if hasattr(v, '__get__'): return v.__get__(None, self)
        return v
    def save(self):
        print('writing', self.variant_id, 'to database')
        return Variant.db.variants.update({'variant_id':self.variant_id},self.__dict__,upsert=True)
    @property
    def status(self):
        return 'M'
    @property
    def HPO(self):
        return []
    @property
    def FILTER(self):
        return self.filter
    @property
    def filter(self):
        self.__dict__['filter']=self.__dict_filter['FILTER']
        return self.__dict__['filter']
    @property
    def hom_samples(self):
        if 'hom_samples' in self.__dict__: return self.__dict__['hom_samples']
        q=vcf.vcf_query(variant_str=self.variant_id)
        self.__dict__.update(q)
        print(self.save())
        return self.__dict__['hom_samples']
    @property
    def het_samples(self):
        if 'het_samples' in self.__dict__: return self.__dict__['het_samples']
        q=vcf.vcf_query(variant_str=self.variant_id)
        self.__dict__.update(q)
        print(self.save())
        return self.__dict__['het_samples']
    def to_JSON(self):
        return json.dumps(self, default=lambda o: o.__dict__, sort_keys=True, indent=4)
    def get_minimal_representation(self): 
        """
        Get the minimal representation of a variant, based on the ref + alt alleles in a VCF
        This is used to make sure that multiallelic variants in different datasets, 
        with different combinations of alternate alleles, can always be matched directly. 
        Note that chromosome is ignored here - in xbrowse, we'll probably be dealing with 1D coordinates 
        Args: 
            pos (int): genomic position in a chromosome (1-based)
            ref (str): ref allele string
            alt (str): alt allele string
        Returns: 
            tuple: (pos, ref, alt) of remapped coordinate
        """
        pos = int(self.pos)
        # If it's a simple SNV, don't remap anything
        if len(self.ref) == 1 and len(self.alt) == 1: return self.pos, self.ref, self.alt
        # strip off identical suffixes
        while(self.alt[-1] == self.ref[-1] and min(len(self.alt),len(self.ref)) > 1):
            alt = alt[:-1]
            ref = ref[:-1]
        # strip off identical prefixes and increment position
        while(self.alt[0] == self.ref[0] and min(len(self.alt),len(self.ref)) > 1):
            alt = self.alt[1:]
            self.ref = self.ref[1:]
            self.pos += 1
        return self.pos, self.ref, self.alt 
    def add_consequence_to_variant(self):
        worst_csq = worst_csq_with_vep(variant['vep_annotations'])
        if worst_csq is None: return
        variant['major_consequence'] = worst_csq['major_consequence']
        variant['HGVSp'] = get_protein_hgvs(worst_csq)
        variant['HGVSc'] = get_transcript_hgvs(worst_csq)
        variant['HGVS'] = get_proper_hgvs(worst_csq)
        variant['CANONICAL'] = worst_csq['CANONICAL']
        variant['flags'] = get_flags_from_variant(variant)
        if csq_order_dict[variant['major_consequence']] <= csq_order_dict["frameshift_variant"]:
            variant['category'] = 'lof_variant'
        elif csq_order_dict[variant['major_consequence']] <= csq_order_dict["missense_variant"]:
            # Should be noted that this grabs inframe deletion, etc.
            variant['category'] = 'missense_variant'
        elif csq_order_dict[variant['major_consequence']] <= csq_order_dict["synonymous_variant"]:
            variant['category'] = 'synonymous_variant'
        else:
            variant['category'] = 'other_variant'
    @property
    def data(self): return self.__dict__
    @property
    def consequence(self):
        """
        Return the most severe consequence
        """
        if 'consequence' in self.__dict__: return self.__dict__['consequence']
        if 'major_consequence' in self.__dict__: return self.__dict__['major_consequence']
        if 'most_severe_consequence' in self.__dict__: return self.__dict__['most_severe_consequence']
        url='http://grch37.rest.ensembl.org/vep/human/hgvs/%s?content-type=application/json' % self.hgvs.replace('chr','')
        r=requests.get(url)
        print(url)
        d=r.json()
        #if not isinstance(d,list) and len(d) < 1: return None
        if 'error' in d: return None
        d=d[0]
        print(d['most_severe_consequence'])
        self.__dict__['consequence']=d['most_severe_consequence']
        print(self.save())
        return self.__dict__['consequence']
    @property
    def transcripts(self):
        if 'transcripts' in self.__dict__: return self.__dict__['transcripts']
        url='http://grch37.rest.ensembl.org/vep/human/hgvs/%s?content-type=application/json' % self.hgvs.replace('chr','')
        r=requests.get(url)
        print(url)
        d=r.json()
        if 'error' in d: return None
        d=d[0]
        self.__dict__['transcripts']=list(set([csq['transcript_id'] for csq in d.transcript_consequences]))
        self.__dict__['genes']=list(set([csq['gene_id'] for csq in d.transcript_consequences]))
        print(self.save())
        if not isinstance(d,list) and len(d) < 1: return None
        return self.__dict__['transcripts']
    @property
    def genes(self):
        if 'genes' in self.__dict__: return list(set(self.__dict__['genes']))
        url='http://grch37.rest.ensembl.org/vep/human/hgvs/%s?content-type=application/json' % self.hgvs.replace('chr','')
        r=requests.get(url)
        print(url)
        d=r.json()[0]
        self.__dict__['genes']=list(set([csq['gene_id'] for csq in d['transcript_consequences']]))
        print(self.save())
        return self.__dict__['genes']
    @property
    def p_hgvs(self):
        """
        Takes consequence dictionary, returns proper variant formatting for synonymous variants
        """
        if '%3D' in csq['HGVSp']:
            try:
                amino_acids = ''.join([protein_letters_1to3[x] for x in csq['Amino_acids']])
                return "p." + amino_acids + csq['Protein_position'] + amino_acids
            except Exception, e:
                print 'Could not create HGVS for: %s' % csq
        return csq['HGVSp'].split(':')[-1]
    @property
    def snpeff(self):
        if 'snpeff' in self.__dict__: return self.__dict__['snpeff']
        self.__dict__['snpeff'] = rest.mv.getvariant('chr%s:g.%s%s>%s'%(self.chrom,self.pos,self.ref,self.alt,),fields='snpeff')
        return self.__dict__['snpeff']
    @property
    def cadd(self):
        if 'cadd' in self.__dict__: return self.__dict__['cadd'].get('phred',None)
        cadd = rest.mv.getvariant('chr%s:g.%s%s>%s'%(self.chrom,self.pos,self.ref,self.alt,),fields='cadd')
        if cadd and 'cadd' in cadd:
            self.__dict__['cadd']=cadd['cadd']
        else:
            self.__dict__['cadd']={}
        print(self.save())
        return self.__dict__['cadd'].get('phred',None)
    @property
    def vep_annotations(self):
        if  'vep_annotations' in self.__dict__: return self.__dict__['vep_annotations']
        self.__dict__['vep_annotations']=rest.vep_anno(self.chrom, self.pos, self.ref, self.alt)
        print('number of transcripts:', len(self.__dict__['vep_annotations']))
        self.__dict__['transcript_consequences']=self.__dict__['vep_annotations'][0]['transcript_consequences']
        self.__dict__['gene_name_upper']=self.__dict__['transcript_consequences'][0]['gene_symbol']
        print('gene_symbol', self.__dict__['gene_name_upper'])
        #print(self.__dict__['vep_annotations'])
        #self.__dict__['vep_annotations'] = order_vep_by_csq(self.__dict__['vep_annotations']) 
        #self.ordered_csqs = [x['major_consequence'] for x in self.__dict__['vep_annotations']]
        # Close but not quite there
        #ordered_csqs = reduce(lambda x, y: ','.join([x, y]) if y not in x else x, ordered_csqs, '').split(',')
        #consequences = defaultdict(lambda: defaultdict(list))
        #for annotation in self.data['vep_annotations']:
            #annotation['HGVS'] = get_proper_hgvs(annotation)
            #consequences[annotation['major_consequence']][annotation['Gene']].append(annotation)
        return self.__dict__['vep_annotations']
    @property
    def transcript_consequences(self):
        if 'transcript_consequences' in self.__dict__: return self.__dict__['transcript_consequences']
        #print(self.vep_annotations)
        return self.__dict__['transcript_consequences']
    @vep_annotations.setter
    def vep_annotations(self,value):
        self.__dict__['vep_annotations']=value
    @property
    def in_exac(self):
        if 'EXAC' in self.__dict__ and len(self.__dict__['EXAC'])>0:
            self.__dict__['in_exac']=True
        else:
            self.__dict__['in_exac']=False
        return self.__dict__['in_exac']
    @property
    def EXAC(self):
        if 'EXAC' in self.__dict__:
            self.__dict__['EXAC']['total_homs']=self.__dict__['EXAC']['AC_Hom']/2
            return 
        if 'EXAC_freq' in self.__dict__: return self.__dict__['EXAC_freq']
        print('EXAC')
        self.__dict__['EXAC_freq']=rest.exac_anno(self.data['variant_id'],update=False)
        if len(self.__dict__['EXAC_freq'])>0:
           self.__dict__['in_exac']=True
        else:
           self.__dict__['in_exac']=False
        #print(self.save())
        return self.__dict__['EXAC_freq']
    @EXAC.setter
    def EXAC(self,value):
        self.__dict__['ExAC_freq']=value
        return self.__dict__['EXAC_freq']
    @property
    def ExAC_freq(self):
        if 'ExAC_freq' in self.__dict__ and 'total_homs' in self.__dict__['ExAC_freq']: return self.__dict__['ExAC_freq']
        self.__dict__['ExAC_freq']=rest.exac_anno(self.variant_id,update=False)
        print(self.__dict__['ExAC_freq'].keys())
        #print(self.save())
        return self.__dict__['ExAC_freq']
    @property
    def WT_COUNT(self):
        if 'WT_COUNT' in self.__dict__: return self.__dict__['WT_COUNT']
        q=vcf.vcf_query(variant_str=self.variant_id)
        if q is None: raise Exception('ERROR',self.variant_id)
        self.__dict__.update(q)
        print(self.save())
        return self.__dict__['WT_COUNT']
    @property
    def HOM_COUNT(self):
        if 'HOM_COUNT' in self.__dict__: return self.__dict__['HOM_COUNT']
        q=vcf.vcf_query(variant_str=self.variant_id)
        if q is None: raise Exception('ERROR',self.variant_id)
        self.__dict__.update(q)
        print(self.save())
        return self.__dict__['HOM_COUNT']
    @property
    def allele_num(self):
        if 'allele_num' in self.__dict__: return self.__dict__['allele_num']
        q=vcf.vcf_query(variant_str=self.variant_id)
        if q is None: raise Exception('ERROR',self.variant_id)
        self.__dict__.update(q)
        print(self.save())
        return self.__dict__['allele_num']
    def get_flags_from_variant(self):
        flags = []
        if 'mnps' in variant:
            flags.append('MNP')
        #lof_annotations = [x for x in variant['vep_annotations'] if x['LoF'] != '']
        lof_annotations = []
        if not len(lof_annotations): return flags
        if all([x['LoF'] == 'LC' for x in lof_annotations]):
            flags.append('LC LoF')
        if all([x['LoF_flags'] != '' for x in lof_annotations]):
            flags.append('LoF flag')
        return flags
    @property
    def HUGO(self):
        if 'gene_name_upper' in self.__dict__: return self.__dict__['gene_name_upper']
        if 'canonical_gene_name_upper' in self.__dict__: return self.__dict__['canonical_gene_name_upper'][0]
        self.vep_annotations
        #print(self.save())
        return self.__dict__['gene_name_upper']
    @property
    def description(self):
        if 'description' in self.__dict__: return self.__dict__['description']
        g=Variant.db.genes.find_one({'gene_name_upper':self.HUGO})
        self.__dict__['description']=g.get('full_gene_name','')
        return self.__dict__['description']
    @property
    def OMIM(self):
        if 'OMIM' in self.__dict__: return self.__dict__['OMIM']
        #self.__dict__['OMIM']=self.vep_annotations[0]['SYMBOL']
        #print(self.save())
        #return self.__dict__['OMIM']
        return ''
    @property
    def p_change(self):
        if 'p_change' in self.__dict__: return self.__dict__['p_change']
        if 'HGVSp' in self.__dict__: return self.__dict__['HGVSp']
        #if 'canonical_hgvsp' in self__dict__: return self.__dict__['canonical_hgvsp']
        self.__dict__['p_change']=dict()
        #self.__dict__['p_change']=
        #trans['hgvsp'].split(':')[1]
        self.__dict__['p_change']['exon']=''
        self.__dict__['p_change']['gene_id']=self.genes[0]
        self.__dict__['p_change']['transcript_id']=self.canonical_transcript[0]
        self.__dict__['p_change']['hgvs_c']=self.canonical_hgvsc[0]
        self.__dict__['p_change']['hgvs_p']=self.canonical_hgvsp[0]
        return self.__dict__['p_change']
    # get db
    def stuff():
        if 'consequence' in self.__dict__ and len(self.__dict__['consequence']): return self.__dict__['consequence']
        pp = pprint.PrettyPrinter(indent=10)
        v['Consequence']=[transcript['consequence_terms'][0] for transcript in v['vep_annotations']['transcript_consequences']]
        v['vep_annotations']['Consequence']=[csq for csq in v['Consequence']]
        print ('CSQ')
        print( v['vep_annotations']['Consequence'] )
        worst_csq = worst_csq_with_vep(variant['vep_annotations'])
        if worst_csq is None: return
        variant['major_consequence'] = worst_csq['major_consequence']
        variant['HGVSp'] = get_protein_hgvs(worst_csq)
        variant['HGVSc'] = get_transcript_hgvs(worst_csq)
        variant['HGVS'] = get_proper_hgvs(worst_csq)
        variant['CANONICAL'] = worst_csq['CANONICAL']
        variant['flags'] = get_flags_from_variant(variant)
        if csq_order_dict[variant['major_consequence']] <= csq_order_dict["frameshift_variant"]:
            variant['category'] = 'lof_variant'
        elif csq_order_dict[variant['major_consequence']] <= csq_order_dict["missense_variant"]:
            # Should be noted that this grabs inframe deletion, etc.
            variant['category'] = 'missense_variant'
        elif csq_order_dict[variant['major_consequence']] <= csq_order_dict["synonymous_variant"]:
            variant['category'] = 'synonymous_variant'
        else:
            variant['category'] = 'other_variant'
    def worst_csq_with_vep(self, annotation_list):
        """
        Takes list of VEP annotations [{'Consequence': 'frameshift', Feature: 'ENST'}, ...]
        Returns most severe annotation (as full VEP annotation [{'Consequence': 'frameshift', Feature: 'ENST'}])
        Also tacks on worst consequence for that annotation (i.e. worst_csq_from_csq)
        :param annotation_list:
        :return worst_annotation:
        """
        if len(annotation_list) == 0: return None
        worst = annotation_list[0]
        for annotation in annotation_list:
            if compare_two_consequences(annotation['Consequence'], worst['Consequence']) < 0:
                worst = annotation
            elif compare_two_consequences(annotation['Consequence'], worst['Consequence']) == 0 and annotation['CANONICAL'] == 'YES':
                worst = annotation
        worst['major_consequence'] = worst_csq_from_csq(worst['Consequence'])
        return worst
    def test():
        client = pymongo.MongoClient()
        hpo_db = client['hpo']
        db = client['uclex-old']
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
            variant=lookups.vcf_query(chrom, pos, ref, alt, individual=patient_id, limit=100)
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
                    g=rest.ensembl_xrefs(gene_id)
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
                    if g and 'hits' in g and 'ensembl' in g['hits'][0]:
                        print g
                        # {u'hits': [{u'_id': u'643669', u'ensembl': [{u'gene': u'ENSG00000262484'}, {u'gene': u'ENSG00000283099'}]}], u'total': 1, u'max_score': 443.8707, u'took': 2}
                        gene_id=find_item(g,'gene')
                        #gene_id=[x for _, x, in g['hits'][0]['ensembl'][0].iteritems()]
                        print gene_id
                        #raise 'hell'
                    else:
                        e=rest.ensembl_region('{}:{}-{}'.format(chrom,pos,pos))
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
    




