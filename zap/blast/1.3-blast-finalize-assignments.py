#!/usr/bin/python

"""
1.3-blast-finalize-assignments.py

This script parses the BLAST output from 1.1-blast-V_assignment.py and 
      1.2-blast-J_assignment.py. Sequences with successful assignments are
      output into fasta files and a master table is created summarizing the
      properties of all input sequences.

Usage:  1.3-blast-finalize-assignments.py -locus <0|1|2|3|4>
                                          -vlib path/to/v-library.fa
					  -jlib path/to/j-library.fa
					  -h

    All options are optional, see below for defaults.
    Invoke with -h or --help to print this documentation.

    locus	0: (DEFAULT) heavy chain (will look for D, as well)
                1: kappa chain
		2: lambda chain
                3: kappa OR lambda
		4: custom library (supply -vlib and -jlib)

Created by Chaim A Schramm on 2013-07-05
Edited and commented for publication by Chaim A Schramm on 2015-02-25.

Copyright (c) 2011-2015 Columbia University and Vaccine Research Center, National
                               Institutes of Health, USA. All rights reserved.

"""

import sys
import os
from zap.blast import *


def find_cdr3_borders(v_id,vgene,vlength,vstart,vend,jgene,jstart,j_start_on_read,jgaps,read_sequence):
	
	'''
	v_id = name of assigned V gene (eg IGHV1-2*02)
	vgene = germline sequence of assigned V gene
	vlength = length of QUERY sequence taken up by match (might be different from blast-reported length and/or vend-vstart+1 because of in-dels)
	vstart = position on germline V gene where match begins (hopefully = 1)
	vend = position on germline V gene where match ends
	jgene = germline sequence of assigned J gene
	jstart = position on germline J gene where match begins
	j_start_on_read = position on query (v-cut version, not full 454 read) where match with germline J begins
	jgaps = blast-reported number of gaps in J assignment
	read_sequence = V(D)J-trimmed sequence of the 454 read
	'''

	vMatches = []
	cys_pat = "TG[T|C|N]" #N is for a couple of shorter V's, like VH4-31
	if re.match("IGLV2-(11|23)", v_id):
		cys_pat = "TGCTGC" #special case
	if re.match("IGHV1-C",v_id):
		cys_pat = "TATGC"
	for m in re.finditer(cys_pat,vgene):
		vMatches.append(m)

	#last one **IN FRAME** is the cysteine we want! (matters for light chains)
	cdr3_start=-1
	vMatches.reverse()
	for cys in vMatches:
		if cys.start() % 3 == 0:
			cdr3_start = vlength - (vend - cys.start())
			break

	# If BLAST has truncated the V gene alignment prior to reaching the conserved cysteine, but still found the J gene,
	#   that likely indicates a large in-del, which must be accounted for, or the start position of CDR 3 will be wrong.
	# The only easy/automatic tool we have is to look for the conserved CxR/K motif; if it's mutated (or we are looking
	#   at a light chain), there's nothing to do. In this case, marking CDR3 as not found is probably preferable to 
	#   keeping the uncorrected sequence, though it should be small effect either way.
	if cdr3_start > vlength:
		has_cxrk, c_start, c_end = has_pat(read_sequence[vlength:], pat_nuc_cxrk)
		if has_cxrk:
			cdr3_start = vlength + c_start
		else:
			cdr3_start = -1

	jMotif = "TGGGG"
	if locus>0 and locus<4: #what if user library is light chains?
		jMotif = "TT[C|T]GG"
	jMatch = re.search(jMotif,jgene)
	
	cdr3_end = vlength + j_start_on_read + (jMatch.start() - jstart) +3

	if jgaps > 0:
		#check for jMotif on read to correct for gaps and get the last one
		#but only check from cdr3 start on and don't let the end move more
		#    than a codon, because there can be similar motifs in CDR3
		wgxg = []
		for m in re.finditer(jMotif, read_sequence[cdr3_start:]):
			wgxg.append(m)
		if len(wgxg) > 0:
			if abs(wgxg[-1].start() + 3 - cdr3_end) <= 3:
				cdr3_end = wgxg.start() + 3


	return cdr3_start, cdr3_end


def main():

	print "curating junction and 3' end..."


        allV_aa      = open ("%s/%s_allV.fa"     % (prj_tree.aa, prj_name), "w" )
        allV_nt      = open( "%s/%s_allV.fa"     % (prj_tree.nt, prj_name), "w" )

        allJ_aa      = open( "%s/%s_allJ.fa"     % (prj_tree.aa, prj_name), "w" )
        allJ_nt      = open( "%s/%s_allJ.fa"     % (prj_tree.nt, prj_name), "w" )

        vj_aa        = open( "%s/%s_goodVJ.fa"   % (prj_tree.aa, prj_name), "w" )
        vj_nt        = open( "%s/%s_goodVJ.fa"   % (prj_tree.nt, prj_name), "w" )

        good_cdr3_aa = open( "%s/%s_goodCDR3.fa" % (prj_tree.aa, prj_name), "w" )
        good_cdr3_nt = open( "%s/%s_goodCDR3.fa" % (prj_tree.nt, prj_name), "w" )

        all_cdr3_nt  = open( "%s/%s_allCDR3.fa"  % (prj_tree.nt, prj_name), "w" )


	#get raw seq stats from temp table
	raw = csv.reader(open("%s/%s_temp_lookup.txt" % (prj_tree.vgene, prj_name),'rU'), delimiter=sep)


	raw_count, total, found, noV, noJ, f_ind  = 0, 0, 0, 0, 0, 1
	counts = {'good':0,'indel':0,'noCDR3':0,'stop':0}

	writer = csv.writer(open("%s/%s_jgerm_tophit.txt" %(prj_tree.tables, prj_name), "w"), delimiter = sep)
	writer.writerow(PARSED_BLAST_HEADER)
	dict_jcounts = dict()

	c = False
	if os.path.isfile("%s/%s_C_001.txt" % (prj_tree.jgene, prj_name)):
		c = True
		dict_ccounts = dict()
		cWriter = csv.writer(open("%s/%s_cgerm_tophit.txt" %(prj_tree.tables, prj_name), "w"), delimiter = sep)
		cWriter.writerow(PARSED_BLAST_HEADER)

	d = False
	if os.path.isfile("%s/%s_D_001.txt" % (prj_tree.jgene, prj_name)):
		d = True
		dict_dcounts = dict()
		dWriter = csv.writer(open("%s/%s_dgerm_tophit.txt" %(prj_tree.tables, prj_name), "w"), delimiter = sep)
		dWriter.writerow(PARSED_BLAST_HEADER)


	seq_stats = csv.writer(open("%s/%s_all_seq_stats.txt"%(prj_tree.tables, prj_name), "w"), delimiter = sep)
	seq_stats.writerow(["id","source_file","source_id","raw_len","trim_len","V_genes","D_genes","J_genes","Ig_class", "indels","stop_codons","V_div","cdr3_nt_len","cdr3_aa_len","cdr3_aa_seq"])

	
	while os.path.isfile("%s/%s_%03d.fasta" % (prj_tree.vgene, prj_name, f_ind)):

		dict_vgerm_aln, dict_other_vgerms, dict_vcounts  =  get_top_hits("%s/%s_%03d.txt"%(prj_tree.vgene, prj_name, f_ind) )
		dict_jgerm_aln, dict_other_jgerms, dict_jcounts  =  get_top_hits("%s/%s_%03d.txt"%(prj_tree.jgene, prj_name, f_ind), topHitWriter=writer, dict_germ_count=dict_jcounts )

		if c:
			minCStartPos = dict( [ (x, dict_jgerm_aln[x].qend) for x in dict_jgerm_aln.keys() ] )
			dict_cgerm_aln, dict_other_cgerms, dict_ccounts  =  get_top_hits("%s/%s_C_%03d.txt"%(prj_tree.jgene, prj_name, f_ind), topHitWriter=cWriter, dict_germ_count=dict_ccounts, minQStart=minCStartPos )

		if d:
			maxDEndPos = dict( [ (x, dict_jgerm_aln[x].qstart) for x in dict_jgerm_aln.keys() ] )
			dict_dgerm_aln, dict_other_dgerms, dict_dcounts  =  get_top_hits("%s/%s_D_%03d.txt"%(prj_tree.jgene, prj_name, f_ind), topHitWriter=dWriter, dict_germ_count=dict_dcounts, maxQEnd=maxDEndPos )

		for entry in SeqIO.parse( "%s/%s_%03d.fasta" % (prj_tree.vgene, prj_name, f_ind), "fasta"):
			total += 1

			try:
				seq_id = str(int(entry.id)) #gets rid of leading zeros to match BLAST
			except:
				seq_id = entry.id


			raw_stats = raw.next()
			raw_count += 1
			while not entry.id == raw_stats[0]:
				#we found a read that did not meet the length cut-off
				seq_stats.writerow(raw_stats + ["NA", "NA", "NA", "NA", "NA", "NA", "NA", "NA", "NA", "NA", "NA"])
				raw_stats = raw.next()
				raw_count += 1


			if not seq_id in dict_vgerm_aln:
				noV+=1
				seq_stats.writerow(raw_stats + ["NA", "NA", "NA", "NA", "NA", "NA", "NA", "NA", "NA", "NA", "NA"])
			elif not seq_id in dict_jgerm_aln:
				noJ+=1
				myV = dict_vgerm_aln[seq_id]
				if (myV.strand == '+'):
					entry.seq = entry.seq[ myV.qstart - 1 :  ]
				else:
					entry.seq = entry.seq[  : myV.qend ].reverse_complement()
				myVgenes = ",".join( [myV.sid] + dict_other_vgerms.get(seq_id,[]) )
				entry.description = "V_gene=%s status=noJ" % (myVgenes)
				allV_nt.write(">%s %s\n%s\n" %(entry.id, entry.description, entry.seq))

				#prevent BioPython errors
				if (len(entry.seq) % 3) > 0:
					entry.seq = entry.seq [ :  -1 * (len(entry.seq) % 3) ]
				allV_aa.write(">%s %s\n%s\n" %(entry.id, entry.description, entry.seq.translate()))
				seq_stats.writerow(raw_stats + [len(entry.seq), myVgenes, "NA", "NA", "NA", "NA", "NA", "NA", "NA", "NA", "NA"])
			else:

				found += 1

				myV = dict_vgerm_aln[seq_id]
				myJ = dict_jgerm_aln[seq_id]
				indel = "no"
				stop = "no"
				cdr3 = True
				
				#get actual V(D)J sequence
				v_len   = myV.qend - (myV.qstart-1) #need to use qstart and qend instead of alignment to account for gaps
				vdj_len = v_len + myJ.qend
				if (myV.strand == '+'):
					entry.seq = entry.seq[ myV.qstart - 1 : myV.qstart + vdj_len - 1 ]
				else:
					entry.seq = entry.seq[ myV.qend - vdj_len : myV.qend ].reverse_complement()

				#get CDR3 boundaries
				cdr3_start,cdr3_end = find_cdr3_borders(myV.sid,dict_v[myV.sid].seq, v_len, min(myV.sstart, myV.send), max(myV.sstart, myV.send), dict_j[myJ.sid].seq, myJ.sstart, myJ.qstart, myJ.gaps, entry.seq.tostring()) #min and max statments take care of switching possible minus strand hit
				cdr3_seq = entry.seq[ cdr3_start : cdr3_end ]

				#push the sequence into frame for translation, if need be
				v_frame = min([myV.sstart, myV.send]) % 3
				five_prime_add = (v_frame-1) % 3
				entry.seq = 'N' * five_prime_add + entry.seq 

				#prevent BioPython errors by trimming to last full codon
				if (len(entry.seq) % 3) > 0:
					entry.seq = entry.seq [ :  -1 * (len(entry.seq) % 3) ]

				#check for stop codons
				if '*' in entry.seq.translate():
					stop = "yes"

				#check for in-frame junction
				if len(cdr3_seq) % 3 != 0:
					indel = "yes"
				else: #even if cdr3 looks ok, might be indels in V and/or J
					j_frame = 3 - ( (dict_j[myJ.sid].seq_len - myJ.sstart - 1) % 3 ) #j genes start in different frames, so caluclate based on end
					frame_shift = (v_len + myJ.qstart - 1) % 3
					if (v_frame + frame_shift) % 3 != j_frame % 3:
						indel = "yes"   #for gDNA we would probably want to distinguish between an out-of-frame recombination and sequencing in-dels in V or J
						                #but that can be ambiguous and for cDNA we can assume that it's sll sequencing in-del anyway, even in CDR3.
					else:
						#use blast gaps to detect frame shift in-dels
						#most of these have stop codons or other sequence problems, but we'll catch a few extra this way
						if ((myV.send-myV.sstart)-(myV.qend-myV.qstart)) % 3 != 0 or ((myJ.send-myJ.sstart)-(myJ.qend-myJ.qstart)) % 3 != 0:
							indel = "yes"

				#make sure cdr3 boundaries make sense
				if (cdr3_end<=cdr3_start or cdr3_end>vdj_len or cdr3_start<0):
					cdr3 = False

				status = "good"
				if not cdr3:
					status = "noCDR3"
				elif indel == "yes":
					status = "indel"
				elif stop == "yes":
					status = "stop"


				#add germline assignments to fasta description and write to disk
				myVgenes = ",".join( [myV.sid] + dict_other_vgerms.get(seq_id,[]) )
				myJgenes = ",".join( [myJ.sid] + dict_other_jgerms.get(seq_id,[]) )
				
				myDgenes = "NA"
				if d:
					if seq_id in dict_dgerm_aln:
						myDgenes = ",".join( [dict_dgerm_aln[seq_id].sid] + dict_other_dgerms.get(seq_id,[]) )
					else:
						myDgenes = "not_found"

				myCgenes = "NA"
				if c:
					if seq_id in dict_cgerm_aln:
						myCgenes = dict_cgerm_aln[seq_id].sid
					else:
						myCgenes = "not_found"
				elif any( x in myV.sid for x in ["LV", "lambda", "Lambda", "LAMBDA"] ):
					myCgenes = "lambda"
				elif any( x in myV.sid for x in ["KV", "kappa", "Kappa", "KAPPA"] ):
					myCgenes = "kappa"
					
				entry.description = "V_gene=%s J_gene=%s D_gene=%s constant=%s status=%s est_V_div=%3.1f%% cdr3_nt_len=%d" % (myVgenes, myJgenes, myDgenes, myCgenes, status, 100-myV.identity, len(cdr3_seq)-6)

				allV_nt.write(">%s %s\n%s\n" %(entry.id, entry.description, entry.seq))
				allV_aa.write(">%s %s\n%s\n" %(entry.id, entry.description, entry.seq.translate()))

				allJ_nt.write(">%s %s\n%s\n" %(entry.id, entry.description, entry.seq))
				allJ_aa.write(">%s %s\n%s\n" %(entry.id, entry.description, entry.seq.translate()))

				if status == "good":
					entry.description += " cdr3_aa_len=%d cdr3_aa_seq=%s" % ((len(cdr3_seq)/3)-2, cdr3_seq.translate())

					vj_nt.write(">%s %s\n%s\n" %(entry.id, entry.description, entry.seq))
					vj_aa.write(">%s %s\n%s\n" %(entry.id, entry.description, entry.seq.translate()))

					good_cdr3_nt.write(">%s %s\n%s\n" %(entry.id, entry.description, cdr3_seq))
					good_cdr3_aa.write(">%s %s\n%s\n" %(entry.id, entry.description, cdr3_seq.translate()))

					all_cdr3_nt.write(">%s %s\n%s\n" %(entry.id, entry.description, cdr3_seq))

					seq_stats.writerow(raw_stats + [len(entry.seq), myVgenes, myDgenes, myJgenes, myCgenes, "no", "no", "%3.1f%%"%(100-myV.identity), "%d"%(len(cdr3_seq)-6), "%d"%(len(cdr3_seq)/3-2), cdr3_seq.translate()])

				elif cdr3:
					#CDR3 but not "good"
					all_cdr3_nt.write(">%s %s\n%s\n" %(entry.id, entry.description, cdr3_seq))
					seq_stats.writerow(raw_stats + [len(entry.seq), myVgenes, myDgenes, myJgenes, myCgenes, "%s"%indel, "%s"%stop, "%3.1f%%"%(100-myV.identity), "%d"%(len(cdr3_seq)-6), "NA", "NA"])
				else:
					seq_stats.writerow(raw_stats + [len(entry.seq), myVgenes, myDgenes, myJgenes, myCgenes, "%s"%indel, "%s"%stop, "%3.1f%%"%(100-myV.identity), "NA", "NA", "NA"])



				counts[status] += 1

		print "%d done, found %d; %d good..." %(total, found, counts['good'])
		f_ind += 1

	#print out some statistics
	handle = open("%s/%s_jgerm_stat.txt" %(prj_tree.tables, prj_name),'w')
	writer 	= csv.writer(handle, delimiter = sep)
	keys 	= sorted(dict_jcounts.keys())
	writer.writerow(["gene", "count", "percent"])
	for key in keys:
		aline = [ key, dict_jcounts[key], "%4.2f" % (dict_jcounts[key] / float(found) * 100) ]
		writer.writerow(aline)
	handle.close()

        if len(dict_ccounts) > 0:
                handle = open("%s/%s_cgerm_stat.txt" %(prj_tree.tables, prj_name),'w')
                writer 	= csv.writer(handle, delimiter = sep)
                keys 	= sorted(dict_ccounts.keys())
                writer.writerow(["gene", "count", "percent"])
                for key in keys:
                        aline = [ key, dict_ccounts[key], "%4.2f" % (dict_ccounts[key] / float(found) * 100) ]
                        writer.writerow(aline)
                handle.close()

        if len(dict_dcounts) > 0:
                handle = open("%s/%s_dgerm_stat.txt" %(prj_tree.tables, prj_name),'w')
                writer 	= csv.writer(handle, delimiter = sep)
                keys 	= sorted(dict_dcounts.keys())
                writer.writerow(["gene", "count", "percent"])
                for key in keys:
                        aline = [ key, dict_dcounts[key], "%4.2f" % (dict_dcounts[key] / float(found) * 100) ]
                        writer.writerow(aline)
                handle.close()

	message = "\nTotal raw reads: %d\nCorrect Length: %d\nV assigned: %d\nJ assigned: %d\nCDR3 assigned: %d\nIn-frame junction/no indels: %d\nContinuous ORF with no stop codons: %d\n\n"  % \
	                                                     (raw_count, total, total-noV, found, found-counts['noCDR3'], found-counts['noCDR3']-counts['indel'], counts['good'])
	print message
	handle = open("%s/finalize_blast.log"%prj_tree.logs, "w")
	handle.write(message)
	handle.close()


if __name__ == '__main__':
	
	#check if I should print documentation
	q = lambda x: x in sys.argv
	if any([q(x) for x in ["h", "-h", "--h", "help", "-help", "--help"]]):
		print __doc__
		sys.exit(0)

	#get parameters from input
	dict_args = processParas(sys.argv, locus="locus", vlib ="vlib", jlib="jlib")
	locus, vlib, jlib = getParasWithDefaults(dict_args, dict(locus=0, vlib="", jlib=""), "locus", "vlib", "jlib")

	#load libraries
	if locus < 4:
		vlib = dict_vgerm_db[locus]
		jlib = dict_jgerm_db[locus]
	elif not os.path.isfile(vlib):
		print "Can't find custom V gene library file!"
		sys.exit(1)
	elif not os.path.isfile(jlib):
		print "Can't find custom J gene library file!"
		sys.exit(1)

	dict_v    =  load_fastas(vlib)
	dict_j    =  load_fastas(jlib)

	prj_tree  = ProjectFolders(os.getcwd())
	prj_name  = fullpath2last_folder(prj_tree.home)

	main()
