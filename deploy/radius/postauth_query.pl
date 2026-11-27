#!/usr/bin/perl
# Finds and rewrites the TOP-LEVEL post-auth { ... } query of FreeRADIUS's SQL queries.conf.
# Used by enable_login_log.sh.
#
#   perl postauth_query.pl has COLUMN FILE   exit 0 when the top-level post-auth block mentions COLUMN
#   perl postauth_query.pl show FILE         print the top-level post-auth block
#   perl postauth_query.pl patch FILE        rewrite its first query so it also writes nasipaddress,
#                                            nasidentifier, calledstationid and callingstationid, and writes
#                                            '' as pass; exit 3 = no such query
#
# The packaged query writes %{User-Password} into radpostauth.pass: the clear text of every PAP login,
# right or wrong. VAULT never stores a readable password, so the patched query leaves pass empty.
#
# The file can also have post-auth { } blocks nested inside accounting { type { ... } } (some FreeRADIUS
# packages do): those write to the accounting tables and must not be touched. So the block is found by
# brace depth (depth 0), with quoted strings, comments and ${...} / %{...} expansions skipped, not by
# its indentation.
use strict;
use warnings;

my $mode = shift @ARGV // '';
my $col  = $mode eq 'has' ? shift @ARGV : '';
my $file = shift @ARGV or die "usage: $0 has COLUMN FILE | show FILE | patch FILE\n";
my $text = do { local $/; open my $fh, '<', $file or die "cannot read $file: $!\n"; <$fh> };

# Same text with comments, strings and ${...}/%{...} blanked out (same length), so that every brace
# left in it is a real block brace.
sub masked {
    my ($t) = @_;
    my $m = $t;
    my ($i, $len) = (0, length $t);
    while ($i < $len) {
        my $c = substr($t, $i, 1);
        my $start = $i;
        if ($c eq '#') {
            my $e = index($t, "\n", $i);
            $i = $e < 0 ? $len : $e;
        } elsif ($c eq '"' || $c eq "'") {
            $i++;
            while ($i < $len) {
                my $x = substr($t, $i, 1);
                if ($x eq '\\') { $i += 2; next }
                last if $x eq $c;
                $i++;
            }
            $i = $i + 1 > $len ? $len : $i + 1;
        } elsif (($c eq '$' || $c eq '%') && substr($t, $i + 1, 1) eq '{') {
            my $depth = 0;
            while ($i < $len) {
                my $x = substr($t, $i, 1);
                $depth++ if $x eq '{';
                if ($x eq '}') { $depth--; if (!$depth) { $i++; last } }
                $i++;
            }
        } else {
            $i++;
            next;
        }
        substr($m, $start, $i - $start) = ' ' x ($i - $start);
    }
    return $m;
}

# (line start, position of "{", position of the matching "}") of the top-level post-auth block.
sub top_block {
    my ($t, $m) = @_;
    my $depth = 0;
    for (my $i = 0; $i < length $m; $i++) {
        my $c = substr($m, $i, 1);
        if ($c eq '{') { $depth++; next }
        if ($c eq '}') { $depth--; next }
        next unless $depth == 0 && substr($m, $i, 9) eq 'post-auth';
        next if $i > 0 && substr($m, $i - 1, 1) !~ /\s/;
        pos($m) = $i;
        next unless $m =~ /\Gpost-auth\s*\{/g;
        my $open = pos($m) - 1;
        my $k = 0;
        for (my $j = $open; $j < length $m; $j++) {
            my $x = substr($m, $j, 1);
            $k++ if $x eq '{';
            if ($x eq '}') { $k--; return (rindex($t, "\n", $i) + 1, $open, $j) if !$k }
        }
        return;
    }
    return;
}

my $m = masked($text);
my ($ls, $open, $close) = top_block($text, $m);

if ($mode eq 'has') {
    exit 1 unless defined $ls;
    my $block = substr($text, $ls, $close - $ls + 1);
    $block =~ s/#[^\n]*//g;                       # a word in a comment does not count
    exit($block =~ /\b\Q$col\E\b/ ? 0 : 1);
}
if ($mode eq 'show') {
    print defined $ls ? substr($text, $ls, $close - $ls + 1) . "\n" : "(no top-level post-auth { } block found)\n";
    exit 0;
}
die "unknown mode '$mode'\n" unless $mode eq 'patch';
exit 3 unless defined $ls;

# The first "query = <string>" directly inside the block (depth 1 relative to it).
my ($qstart, $qend);
my $depth = 0;
for (my $i = $open + 1; $i < $close; $i++) {
    my $c = substr($m, $i, 1);
    if ($c eq '{') { $depth++; next }
    if ($c eq '}') { $depth--; next }
    next unless $depth == 0 && substr($m, $i, 5) eq 'query' && substr($m, $i - 1, 1) =~ /\s/;
    pos($m) = $i;
    next unless $m =~ /\Gquery\s*=/g;
    my $s = pos($m);
    $s++ while substr($text, $s, 1) =~ /[ \t]/;      # in $text: the string itself is blank in $m
    next unless substr($text, $s, 1) eq '"';
    my $e = $s + 1;
    while ($e < $close) {
        my $x = substr($text, $e, 1);
        if ($x eq '\\') { $e += 2; next }
        last if $x eq '"';
        $e++;
    }
    ($qstart, $qend) = ($s, $e);
    last;
}
exit 3 unless defined $qstart;

my $old = substr($text, $qstart, $qend - $qstart + 1);
my $nl  = $text =~ /\r\n/ ? "\r\n" : "\n";
my $ts  = $old =~ /'(%S(?:\.%M)?)'/ ? $1 : '%S';       # '%S' on 3.0, '%S.%M' on 3.2
my $cls = $old =~ /\$\{\.\.class\.column_name\}/;      # optional Class column (3.2)
my $q = "\"\\$nl"
    . "\t\tINSERT INTO \${..postauth_table} \\$nl"
    . "\t\t\t(username, pass, reply, authdate, nasipaddress, nasidentifier, calledstationid, callingstationid"
    . ($cls ? " \${..class.column_name}" : '') . ") \\$nl"
    . "\t\tVALUES ( \\$nl"
    . "\t\t\t'%{SQL-User-Name}', \\$nl"
    . "\t\t\t'', \\$nl"      # pass: never the typed password
    . "\t\t\t'%{reply:Packet-Type}', \\$nl"
    . "\t\t\t'$ts', \\$nl"
    . "\t\t\t'%{%{NAS-IP-Address}:-%{Packet-Src-IP-Address}}', \\$nl"
    . "\t\t\t'%{NAS-Identifier}', \\$nl"
    . "\t\t\t'%{Called-Station-Id}', \\$nl"
    . "\t\t\t'%{Calling-Station-Id}'"
    . ($cls ? " \\$nl\t\t\t\${..class.reply_xlat})\"" : ')"');
substr($text, $qstart, $qend - $qstart + 1) = $q;

open my $out, '>', $file or die "cannot write $file: $!\n";     # in place: owner and mode are kept
print {$out} $text;
close $out or die "cannot write $file: $!\n";
exit 0;
