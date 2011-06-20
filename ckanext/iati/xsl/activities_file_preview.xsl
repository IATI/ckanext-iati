<?xml version="1.0"?>
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">

<xsl:template  match="activity-date">
    <xsl:value-of select="./@iso-date" />
</xsl:template>


<xsl:template match="iati-activities">
    <table width="100%">
        <thead>
            <tr>
                <th>
                    <xsl:attribute name="class">activity-title</xsl:attribute>
                    Activity Title
                </th>
                <th>
                    <xsl:attribute name="class">activity-status</xsl:attribute>
                    Status
                </th>
                <th>
                    <xsl:attribute name="class">activity-dates</xsl:attribute>
                    Start and End Dates
                </th>
            </tr>
        </thead>
        <tbody>
      <xsl:for-each select="iati-activity[position() &lt; 10]">
        
            <tr>
                <td>
                    <xsl:attribute name="class">activity-title</xsl:attribute>
                    <xsl:attribute name="class">titlecased</xsl:attribute>
                    <xsl:value-of select="title" /> 
                </td>
                <td>
                    <xsl:attribute name="class">activity-status</xsl:attribute>
                    <xsl:value-of select="activity-status" />
                </td>
                <td>
                    <xsl:attribute name="class">date</xsl:attribute>
                    <xsl:apply-templates select="activity-date[@type='start']" />
                    &#x2014;
                    <xsl:apply-templates select="activity-date[@type='end']" />
                </td>
            </tr>
        
      </xsl:for-each>
      
      </tbody>
      <tfoot>
        <tr>
            <th colspan="3"><span style="float: right;">(Listing at most 10 entries)</span></th>
        </tr>
    </tfoot>
    </table>
</xsl:template>

</xsl:stylesheet>

