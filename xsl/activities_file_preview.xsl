<?xml version="1.0"?>
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">




<xsl:template  match="activity-date">
    <xsl:value-of select="./@iso-date" />
</xsl:template>




<xsl:template match="budget-planned">
    <td>
        <xsl:choose>
            <xsl:when test="@type = 'commitment'" >
                   Budget - Commitment
            </xsl:when>
        </xsl:choose> 
    </td>
    <td>
        <xsl:attribute name="class">date</xsl:attribute>
        <xsl:value-of select="value/@value-date"/>
    </td>
    <td>
        <xsl:attribute name="class">amount</xsl:attribute>
        <xsl:value-of select="value"/>
    </td>
    <td>
        <xsl:attribute name="class">date</xsl:attribute>
        <xsl:value-of select="period-start"/>
    </td>
    <td>
        <xsl:attribute name="class">date</xsl:attribute>
        <xsl:value-of select="period-end"/>
    </td>
</xsl:template>




<xsl:template match="transaction">
    <td>
        <xsl:choose>
            <xsl:when test="@type = 'disbursement'" >
                   Transaction - Disbursement
            </xsl:when>
        </xsl:choose> 
    </td>
    <td>
        <xsl:attribute name="class">date</xsl:attribute>
        <xsl:value-of select="value/@value-date"/>
    </td>
    <td>
        <xsl:attribute name="class">amount</xsl:attribute>
        <xsl:value-of select="value"/>
    </td>
    <td>
        <xsl:attribute name="class">date</xsl:attribute>
        &#x2014;
    </td>
    <td>
        <xsl:attribute name="class">date</xsl:attribute>
        &#x2014;
    </td>
</xsl:template>



<xsl:template match="iati-activity">
    <table>
        <xsl:attribute name="class">iati-activity</xsl:attribute>
        <thead>
            <tr>
                <th> Budgets/Transations </th>
                <th> Date </th>
                <th> Amount </th>
                <th> Start </th>
                <th> End </th>
            </tr>
        </thead>
        <tbody>
            <xsl:for-each select="budget-planned|transaction">
                <tr>
                    <xsl:if test="position() mod 2 != 1">
                        <xsl:attribute name="class">evenrow</xsl:attribute>
                    </xsl:if>
                    <xsl:apply-templates select="." />
                </tr>
            </xsl:for-each>
        </tbody>
    </table>
</xsl:template>





<xsl:template match="iati-activities">
        <thead>
            <tr>
                <th>
                    <xsl:attribute name="class">activity-title</xsl:attribute>
                    <xsl:attribute name="colspan">2</xsl:attribute>
                    Activity Title
                </th>
                <th>
                    <xsl:attribute name="class">activity-status</xsl:attribute>
                    Status
                </th>
                <th>
                    <xsl:attribute name="class">activity-dates</xsl:attribute>
                    Stard and End Dates
                </th>
            </tr>
        </thead>
      <xsl:for-each select="iati-activity">
        <tbody>
            <tr>
                <td>
                    <img>
                        <xsl:attribute name="class">activityexpand</xsl:attribute>
                        <xsl:attribute name="src">images/iatiminus.png</xsl:attribute>
                        <xsl:attribute name="alt">-</xsl:attribute>
                    </img>
                </td>
                <td>
                    <xsl:attribute name="class">activity-title</xsl:attribute>
                    <xsl:value-of select="title" />
                </td>
                <td>
                    <xsl:value-of select="activity-status" />
                </td>
                <td>
                    <xsl:attribute name="class">date</xsl:attribute>
                    <xsl:apply-templates select="activity-date[@type='start']" />
                    &#x2014;
                    <xsl:apply-templates select="activity-date[@type='end']" />
                </td>
            </tr>
            <tr>
                <xsl:attribute name="class">collapsed</xsl:attribute>
                <td></td>
                <td>
                    <xsl:attribute name="colspan">3</xsl:attribute>
                    <xsl:value-of select="description" />
                </td>
            </tr>
            <tr>
                <xsl:attribute name="class">collapsed</xsl:attribute>
                <td></td>
                <td>
                    <xsl:attribute name="colspan">3</xsl:attribute>
                    <xsl:apply-templates select="." />
                </td>
            </tr>
        </tbody>
      </xsl:for-each>
</xsl:template>

</xsl:stylesheet>

